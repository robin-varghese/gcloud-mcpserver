#!/usr/bin/env python3
"""
Interactive Client for Google Cloud Monitoring MCP Server

This script provides a REPL interface to interact with the Monitoring MCP server
using natural language. It uses Gemini to translate requests into tool calls.
"""

import asyncio
import os
import sys
import json
from typing import Any, Dict, List, Optional
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from google import genai
from google.genai import types

# Configuration
DOCKER_IMAGE = "gcloud-monitoring-mcp-image"
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

def translate_to_tool_call(prompt: str, project_id: str) -> Dict[str, Any]:
    """Translate natural language prompt to a tool call using Gemini."""
    if not GOOGLE_API_KEY:
        return None

    try:
        client = genai.Client(api_key=GOOGLE_API_KEY)
        
        system_instruction = f"""
        You are an expert Google Cloud Monitoring assistant.
        Translate the user's natural language request into a valid MCP tool call.
        
        Available Tools:
        1. query_time_series
           - project_id: str
           - metric_type: str (e.g., 'compute.googleapis.com/instance/cpu/utilization')
           - resource_filter: str (e.g., 'resource.labels.instance_id="123"')
           - minutes_ago: int
           
        2. query_logs
           - project_id: str
           - filter: str (e.g., 'severity>=ERROR')
           - hours_ago: int
           - limit: int
           
        3. list_metrics
           - project_id: str
           - filter: str (optional)

        Current Project ID: {project_id}
        
        Output JSON ONLY. Format:
        {{
            "tool": "tool_name",
            "arguments": {{ ... }}
        }}
        
        Example 1:
        User: "show cpu usage for vm instance-1"
        Output:
        {{
            "tool": "query_time_series",
            "arguments": {{
                "project_id": "{project_id}",
                "metric_type": "compute.googleapis.com/instance/cpu/utilization",
                "resource_filter": "resource.labels.instance_id=\\"instance-1\\"",
                "minutes_ago": 60
            }}
        }}
        
        Example 2:
        User: "show error logs from last hour"
        Output:
        {{
            "tool": "query_logs",
            "arguments": {{
                "project_id": "{project_id}",
                "filter": "severity>=ERROR",
                "hours_ago": 1,
                "limit": 20
            }}
        }}
        """
        
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=0.1,
                response_mime_type="application/json"
            )
        )
        
        return json.loads(response.text)
    except Exception as e:
        print(f"⚠️ NLP Translation failed: {e}")
        return None

async def run_interactive_session():
    print(f"Starting Interactive Monitoring MCP Client...")
    
    # Check for API key
    global GOOGLE_API_KEY
    if not GOOGLE_API_KEY:
        print("⚠️ GOOGLE_API_KEY not found in environment variables.")
        user_key = input("Enter your Google API Key to enable NLP (or press Enter to skip): ").strip()
        if user_key:
            GOOGLE_API_KEY = user_key
            
    if not GOOGLE_API_KEY:
        print("❌ NLP features require an API Key. Exiting.")
        return

    # Get Project ID
    project_id = input("Enter your GCP Project ID: ").strip()
    if not project_id:
        print("Project ID is required.")
        return

    print(f"Connecting to server via: docker run ... {DOCKER_IMAGE}")
    
    try:
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                # Initialize connection
                await session.initialize()
                print("\n✅ Connected to Monitoring MCP Server")
                print("\n" + "="*50)
                print("ENTER REQUESTS (type 'exit' or 'quit' to stop)")
                print("Examples:")
                print("  > show cpu utilization for my vm")
                print("  > list all compute metrics")
                print("  > show error logs from the last 2 hours")
                print("="*50 + "\n")

                while True:
                    try:
                        # Get user input
                        user_input = input("\nmonitor> ").strip()
                        
                        if not user_input:
                            continue
                            
                        if user_input.lower() in ['exit', 'quit']:
                            print("Exiting session.")
                            break
                        
                        # Translate NLP to tool call
                        print("🤔 Thinking...")
                        tool_call = translate_to_tool_call(user_input, project_id)
                        
                        if not tool_call:
                            print("Could not understand request.")
                            continue
                            
                        tool_name = tool_call["tool"]
                        args = tool_call["arguments"]
                        
                        print(f"Executing Tool: {tool_name}")
                        print(f"Arguments: {json.dumps(args, indent=2)}")
                        
                        # Call the tool
                        result = await session.call_tool(tool_name, arguments=args)
                        
                        # Print results
                        for content in result.content:
                            if content.type == "text":
                                # Try to pretty print JSON output
                                try:
                                    data = json.loads(content.text)
                                    
                                    if tool_name == "query_time_series":
                                        count = data.get("time_series_count", 0)
                                        print(f"\nFound {count} time series.")
                                        if count > 0:
                                            # Show first series preview
                                            ts = data["time_series"][0]
                                            print("First Series Preview:")
                                            print(f"Resource: {ts['resource']}")
                                            if ts['points']:
                                                latest = ts['points'][0]['value']
                                                val = latest.get('double_value') or latest.get('int64_value')
                                                print(f"Latest Value: {val}")
                                                
                                    elif tool_name == "query_logs":
                                        count = data.get("log_entry_count", 0)
                                        print(f"\n{'='*80}")
                                        print(f"Found {count} log entries")
                                        print(f"{'='*80}\n")
                                        
                                        for i, entry in enumerate(data.get("log_entries", []), 1):
                                            print(f"Entry #{i}:")
                                            print(f"  Log Name: {entry.get('log_name', 'N/A')}")
                                            print(f"  Timestamp: {entry.get('timestamp', 'N/A')}")
                                            print(f"  Severity: {entry.get('severity', 'N/A')}")
                                            print(f"  Resource Type: {entry.get('resource', {}).get('type', 'N/A')}")
                                            
                                            # Show resource labels
                                            labels = entry.get('resource', {}).get('labels', {})
                                            if labels:
                                                print(f"  Resource Labels:")
                                                for k, v in labels.items():
                                                    print(f"    {k}: {v}")
                                            
                                            # Show text payload
                                            if entry.get('text_payload'):
                                                print(f"  Text Payload:")
                                                print(f"    {entry['text_payload']}")
                                            
                                            # Show JSON payload
                                            if entry.get('json_payload'):
                                                print(f"  JSON Payload:")
                                                payload_str = json.dumps(entry['json_payload'], indent=4)
                                                for line in payload_str.split('\n'):
                                                    print(f"    {line}")
                                            
                                            print()  # Blank line between entries

                                            
                                    elif tool_name == "list_metrics":
                                        count = data.get("metric_count", 0)
                                        print(f"\nFound {count} metrics.")
                                        for m in data.get("metrics", [])[:5]:
                                            print(f"- {m['type']}: {m['display_name']}")
                                    else:
                                        print(json.dumps(data, indent=2))
                                        
                                except json.JSONDecodeError as e:
                                    print(f"JSON decode error: {e}")
                                    print(content.text)
                                except Exception as e:
                                    print(f"Error processing result: {e}")
                                    import traceback
                                    traceback.print_exc()
                            else:
                                print(f"[{content.type} content]")
                                
                    except KeyboardInterrupt:
                        print("\nOperation cancelled.")
                    except Exception as e:
                        print(f"Error: {str(e)}")
                        import traceback
                        traceback.print_exc()
                        
    except Exception as e:
        print(f"\nFailed to connect to MCP server: {e}")

if __name__ == "__main__":
    try:
        asyncio.run(run_interactive_session())
    except KeyboardInterrupt:
        print("\nExiting...")
