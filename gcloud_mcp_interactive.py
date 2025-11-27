#!/usr/bin/env python3
"""
Interactive Client for GCloud MCP Server

This script provides a REPL (Read-Eval-Print Loop) interface to interact with the 
GCloud MCP server. It allows you to execute arbitrary gcloud commands dynamically.
"""

import asyncio
import os
import sys
import shlex
import json
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from google import genai
from google.genai import types

# Configuration
DOCKER_IMAGE = "gcloud-mcp-image"
MOUNT_PATH = f"{os.path.expanduser('~')}/.config/gcloud:/root/.config/gcloud"
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")

# Server parameters
server_params = StdioServerParameters(
    command="docker",
    args=[
        "run",
        "-i",
        "--rm",
        "--network", "host",
        "-v", MOUNT_PATH,
        DOCKER_IMAGE
    ],
    env=None
)

def translate_to_gcloud(prompt: str) -> str:
    """Translate natural language prompt to gcloud command using Gemini."""
    if not GOOGLE_API_KEY:
        return prompt  # Fallback if no API key

    try:
        client = genai.Client(api_key=GOOGLE_API_KEY)
        
        system_instruction = """
        You are an expert Google Cloud CLI (gcloud) assistant.
        Translate the user's natural language request into a valid 'gcloud' command.
        
        Rules:
        1. Return ONLY the command arguments (exclude 'gcloud' prefix).
        2. If the user input is already a valid command (starts with known gcloud groups like 'compute', 'projects', 'storage'), return it as is.
        3. Ensure flags are correct (e.g., --project, --zone).
        4. Output raw text only, no markdown formatting.
        5. NEVER use placeholders like NEW_MACHINE_TYPE, PROJECT_ID, etc. Use actual values or inform the user what's needed.
        6. If insufficient information is provided, return a helpful error message starting with "Need more info:"
        7. For multi-step operations (stop, upgrade, start), return with "Multi-step:" prefix and separate with " && "
        8. BE SMART: When zone is missing for upgrade/downgrade, suggest listing VMs first to get the zone.
        
        Google Cloud Machine Type Sizes (smallest to largest):
        - E2 series: e2-micro → e2-small → e2-medium → e2-standard-2 → e2-standard-4 → e2-standard-8
        - N1 series: f1-micro → g1-small → n1-standard-1 → n1-standard-2 → n1-standard-4 → n1-standard-8
        - N2 series: n2-standard-2 → n2-standard-4 → n2-standard-8 → n2-standard-16
        
        **Context-Aware Behavior:**
        - "downgrade" = change to a smaller machine type (if current type unknown, suggest listing first)
        - "upgrade" = change to a larger machine type
        - "smallest" or "micro" = e2-micro or f1-micro
        
        IMPORTANT: Changing machine type requires stopping the instance first!
        
        When user asks to upgrade/downgrade WITHOUT providing zone:
        - If they just want to see info: Output: compute instances list --format="table(name,zone,machineType,status)"
        - If they want to change: Output: Need more info: First run 'list all vms' to see the zone and current machine type, then ask: 'stop, downgrade to e2-micro, and restart <instance> in zone <zone>'
        
        When user asks to upgrade/downgrade WITH zone but without target type:
        - "downgrade": assume one step down in same series or to e2-micro if unknown
        - "upgrade": assume one step up in same series
        
        Example Flows:
        User: "downgrade instance-1"
        Output: compute instances list --format="table(name,zone,machineType,status)"
        
        User: "downgrade instance-1 to e2-micro in zone us-central1-a"
        Output: Multi-step: compute instances stop instance-1 --zone us-central1-a && compute instances set-machine-type instance-1 --machine-type e2-micro --zone us-central1-a && compute instances start instance-1 --zone us-central1-a
        
        User: "list all vms"
        Output: compute instances list
        
        User: "stop, upgrade to e2-small, and restart instance-1 in zone us-central1-a"
        Output: Multi-step: compute instances stop instance-1 --zone us-central1-a && compute instances set-machine-type instance-1 --machine-type e2-small --zone us-central1-a && compute instances start instance-1 --zone us-central1-a
        """
        
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=0.1
            )
        )
        
        return response.text.strip()
    except Exception as e:
        print(f"⚠️ NLP Translation failed: {e}")
        return prompt

def humanize_error(error_text: str) -> str:
    """Convert technical gcloud errors into friendly, actionable messages."""
    import re
    
    # Special case: set-machine-type failures (instance likely running)
    if "set-machine-type" in error_text and ("not found" in error_text.lower() or "cannot" in error_text.lower()):
        return ("❌ Cannot change machine type while instance is running.\n"
                "💡 To upgrade your instance:\n"
                "   1. Stop it: 'compute instances stop <instance-name> --zone <zone>'\n"
                "   2. Change type: 'compute instances set-machine-type <instance-name> --machine-type <new-type> --zone <zone>'\n"
                "   3. Start it: 'compute instances start <instance-name> --zone <zone>'\n"
                "   \n"
                "   Or ask: 'stop, upgrade to e2-small, and restart instance <name> in zone <zone>'")
    
    # Pattern: Missing flag
    if "Specify the [--zone] flag" in error_text or "--zone" in error_text:
        return ("❌ Oops! The instance zone is missing.\n"
                "💡 Please specify the zone where your instance is located.\n"
                "   Example: us-central1-a, europe-west1-b\n"
                "   Try: 'list all vms' to see zones.")
    
    if "Specify the [--region] flag" in error_text or "--region" in error_text:
        return ("❌ Oops! The region is missing.\n"
                "💡 Please specify the region for this resource.\n"
                "   Example: us-central1, europe-west1")
    
    if "Specify the [--project] flag" in error_text or "--project" in error_text:
        return ("❌ Oops! The project ID is missing.\n"
                "💡 Please specify your GCP project ID.\n"
                "   Try: 'gcloud config get-value project' to see your default project.")
    
    # Pattern: Resource not found
    if "was not found" in error_text or "Could not fetch resource" in error_text:
        return ("❌ Resource not found.\n"
                "💡 The resource might not exist, or you may not have permission to access it.\n"
                "   Double-check the name and try listing resources first.")
    
    # Pattern: Permission denied
    if "PERMISSION_DENIED" in error_text or "does not have permission" in error_text:
        return ("❌ Permission denied.\n"
                "💡 Your account doesn't have the required permissions for this operation.\n"
                "   Contact your GCP admin or check IAM roles.")
    
    # Pattern: Invalid value
    match = re.search(r"Invalid value for \[([^\]]+)\]", error_text)
    if match:
        field = match.group(1)
        return (f"❌ Invalid value provided for '{field}'.\n"
                f"💡 Please provide a valid value for this field.\n"
                f"   Check the documentation for accepted values.")
    
    # Default: Show original error but with friendly intro
    return (f"❌ Command failed:\n{error_text}\n\n"
            f"💡 Tip: Try being more specific or check 'gcloud help <command>' for usage.")

async def run_interactive_session():
    print(f"Starting Interactive GCloud MCP Client...")
    
    # Check for API key
    global GOOGLE_API_KEY
    if not GOOGLE_API_KEY:
        print("⚠️ GOOGLE_API_KEY not found in environment variables.")
        user_key = input("Enter your Google API Key to enable NLP (or press Enter to skip): ").strip()
        if user_key:
            GOOGLE_API_KEY = user_key
            
    if not GOOGLE_API_KEY:
        print("⚠️ NLP features disabled. Only exact gcloud commands will work.")
    else:
        print("✨ NLP Enabled: You can use natural language (e.g., 'list my vms')")
        
    print(f"Connecting to server via: docker run ... {DOCKER_IMAGE}")
    
    try:
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                # Initialize connection
                await session.initialize()
                print("\n✅ Connected to GCloud MCP Server")
                
                # List tools to confirm connection
                tools = await session.list_tools()
                print(f"Available Tools: {[t.name for t in tools.tools]}")
                print("\n" + "="*50)
                print("ENTER COMMANDS (type 'exit' or 'quit' to stop)")
                print("Examples:")
                print("  > list all projects")
                print("  > compute instances list")
                print("="*50 + "\n")

                while True:
                    try:
                        # Get user input
                        user_input = input("\ngcloud> ").strip()
                        
                        if not user_input:
                            continue
                            
                        if user_input.lower() in ['exit', 'quit']:
                            print("Exiting session.")
                            break
                        
                        # Translate NLP to gcloud command
                        command_args_str = translate_to_gcloud(user_input)
                        
                        # Check if Gemini is asking for more information
                        if command_args_str.startswith("Need more info:"):
                            print(f"\n💡 {command_args_str[15:].strip()}")
                            continue
                        
                        # Check if this is a multi-step command
                        if command_args_str.startswith("Multi-step:"):
                            steps = command_args_str[11:].strip().split(" && ")
                            print(f"\n🔄 Executing {len(steps)}-step operation:")
                            for i, step in enumerate(steps, 1):
                                step_args = shlex.split(step)
                                if step_args and step_args[0] == 'gcloud':
                                    step_args = step_args[1:]
                                
                                print(f"\n  Step {i}/{len(steps)}: gcloud {' '.join(step_args)} ...")
                                
                                try:
                                    result = await session.call_tool(
                                        "run_gcloud_command",
                                        arguments={"args": step_args}
                                    )
                                    
                                    # Print results
                                    for content in result.content:
                                        if content.type == "text":
                                            # Only treat as error if it contains "ERROR:" keyword
                                            if "ERROR:" in content.text:
                                                print(humanize_error(content.text))
                                                print(f"\n❌ Multi-step operation stopped at step {i}")
                                                break
                                            else:
                                                # For final step, extract useful info from STDERR
                                                if i == len(steps):
                                                    # Extract IP addresses if present
                                                    import re
                                                    internal_ip = re.search(r'Instance internal IP is ([\d.]+)', content.text)
                                                    external_ip = re.search(r'Instance external IP is ([\d.]+)', content.text)
                                                    
                                                    if internal_ip or external_ip:
                                                        print(f"  ✓ Step {i} completed")
                                                        if internal_ip:
                                                            print(f"    Internal IP: {internal_ip.group(1)}")
                                                        if external_ip:
                                                            print(f"    External IP: {external_ip.group(1)}")
                                                    else:
                                                        print(f"  ✓ Step {i} completed")
                                                else:
                                                    # Intermediate steps: just show brief success
                                                    print(f"  ✓ Step {i} completed")
                                        else:
                                            print(f"[{content.type} content]")
                                    else:
                                        continue  # Continue to next step
                                    break  # Break outer loop if error
                                except Exception as e:
                                    print(f"  ❌ Step {i} failed: {str(e)}")
                                    break
                            continue
                        
                        # Parse into list
                        args = shlex.split(command_args_str)
                        
                        # Remove 'gcloud' prefix if present (LLM might add it despite instructions)
                        if args and args[0] == 'gcloud':
                            args = args[1:]
                            
                        print(f"Executing: gcloud {' '.join(args)} ...")
                        
                        # Call the tool
                        result = await session.call_tool(
                            "run_gcloud_command",
                            arguments={"args": args}
                        )
                        
                        # Print results
                        for content in result.content:
                            if content.type == "text":
                                # Check if this is an error message (only if contains ERROR:)
                                if "ERROR:" in content.text:
                                    print(humanize_error(content.text))
                                else:
                                    print(content.text)
                            else:
                                print(f"[{content.type} content]")
                                
                    except KeyboardInterrupt:
                        print("\nOperation cancelled.")
                    except Exception as e:
                        print(f"Error: {str(e)}")
                        
    except Exception as e:
        print(f"\nFailed to connect to MCP server: {e}")
        print("Ensure the Docker image is built and gcloud credentials are mounted correctly.")

if __name__ == "__main__":
    try:
        asyncio.run(run_interactive_session())
    except KeyboardInterrupt:
        print("\nExiting...")
