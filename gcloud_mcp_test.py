import asyncio
import os
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# Define the Docker command to run the MCP server
# We mount the host's gcloud config to share credentials
# We use --network host to ensure access to Google Cloud APIs
server_params = StdioServerParameters(
    command="docker",
    args=[
        "run",
        "-i",
        "--rm",
        "--network", "host",
        # Mount as read-write because gcloud needs to write logs and lock files
        "-v", f"{os.path.expanduser('~')}/.config/gcloud:/root/.config/gcloud",
        "gcloud-mcp-image"
    ],
    env=None # Inherit env if needed, or set specific ones
)

async def run_test():
    print("Starting MCP Client...")
    print(f"Connecting to server via command: {server_params.command} {' '.join(server_params.args)}")
    
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            # Initialize the connection
            await session.initialize()

            # List available tools
            print("\n[1] Listing Available Tools:")
            tools = await session.list_tools()
            for tool in tools.tools:
                print(f"  - {tool.name}: {tool.description[:50]}...")

            # Example: Run a generic gcloud command
            # The tool expects 'args' as a list of strings, representing the gcloud command arguments
            print("\n[2] Testing Tool: run_gcloud_command (gcloud projects list)")
            try:
                # We pass the arguments for 'gcloud projects list' as a list: ["projects", "list"]
                result = await session.call_tool("run_gcloud_command", arguments={"args": ["projects", "list"]})
                print("Result:")
                print(result.content)
            except Exception as e:
                print(f"Error calling run_gcloud_command: {e}")
                
            # Example: List GCS Buckets using run_gcloud_command
            print("\n[3] Testing Tool: run_gcloud_command (gcloud storage buckets list)")
            try:
                result = await session.call_tool("run_gcloud_command", arguments={"args": ["storage", "buckets", "list", "--format=json"]})
                print("Result (first 200 chars):")
                # content is usually a list of TextContent or ImageContent
                for content in result.content:
                    if hasattr(content, 'text'):
                        print(content.text[:200] + "...")
            except Exception as e:
                print(f"Error calling run_gcloud_command for buckets: {e}")

            # [4] List VMs and Get CPU Utilization
            print("\n[4] VM Verification Step")
            project_id = input("Enter Project ID to list VMs: ").strip()
            if project_id:
                print(f"\nListing VMs for project: {project_id}...")
                try:
                    # List all VMs in all regions
                    vm_result = await session.call_tool("run_gcloud_command", arguments={
                        "args": ["compute", "instances", "list", "--project", project_id, "--format=json"]
                    })
                    
                    import json
                    vms = []
                    for content in vm_result.content:
                        if hasattr(content, 'text'):
                            try:
                                vms = json.loads(content.text)
                                break
                            except json.JSONDecodeError:
                                continue
                    
                    if not vms:
                        print("No VMs found or failed to parse output.")
                        print("Raw Output:")
                        for content in vm_result.content:
                            if hasattr(content, 'text'):
                                print(content.text)
                    else:
                        print(f"Found {len(vms)} VMs.")
                        from datetime import datetime, timedelta, timezone
                        
                        # Get time interval for last 5 minutes (RFC3339 format)
                        now = datetime.now(timezone.utc)
                        start_time = (now - timedelta(minutes=5)).isoformat()
                        end_time = now.isoformat()
                        interval = f"{start_time},{end_time}"

                        for vm in vms:
                            name = vm.get('name')
                            zone = vm.get('zone', '').split('/')[-1]
                            status = vm.get('status')
                            print(f"\nVM: {name} (Zone: {zone}, Status: {status})")
                            
                            if status == "RUNNING":
                                print("  Fetching CPU Utilization...")
                                # Construct filter for this specific instance
                                metric_filter = f'metric.type="compute.googleapis.com/instance/cpu/utilization" AND resource.type="gce_instance" AND resource.labels.instance_id="{vm.get("id")}"'
                                
                                try:
                                    # Use 'gcloud monitoring read' instead of 'time-series list'
                                    metric_query = f'compute.googleapis.com/instance/cpu/utilization{{resource.instance_id="{vm.get("id")}"}}'
                                    
                                    cpu_result = await session.call_tool("run_gcloud_command", arguments={
                                        "args": [
                                            "monitoring", "read",
                                            metric_query,
                                            "--start", start_time,
                                            "--end", end_time,
                                            "--project", project_id,
                                            "--format=json"
                                        ]
                                    })
                                    
                                    print(f"  Debug - Raw CPU response:")
                                    cpu_data = []
                                    for c in cpu_result.content:
                                        if hasattr(c, 'text'):
                                            print(f"  {c.text[:500]}")
                                            try:
                                                cpu_data = json.loads(c.text)
                                                break
                                            except: continue
                                    
                                    if cpu_data:
                                        print(f"  Debug - Parsed {len(cpu_data)} time series")
                                        if len(cpu_data) > 0 and 'points' in cpu_data[0]:
                                            print(f"  Debug - Found {len(cpu_data[0]['points'])} points")
                                            latest_point = cpu_data[0]['points'][0]
                                            utilization = latest_point['value']['doubleValue']
                                            print(f"  CPU Utilization: {utilization * 100:.2f}%")
                                        else:
                                            print("  CPU Utilization: No data points in response")
                                    else:
                                        print("  CPU Utilization: No data available (VM might be newly created or monitoring disabled)")
                                except Exception as e:
                                    print(f"  Error fetching CPU metrics: {e}")
                                    import traceback
                                    traceback.print_exc()
                            else:
                                print("  Skipping CPU check (VM is not RUNNING)")

                except Exception as e:
                    print(f"Error listing VMs: {e}")
            else:
                print("Skipping VM verification (no Project ID provided).")

if __name__ == "__main__":
    # Check if mcp is installed
    try:
        import mcp
        asyncio.run(run_test())
    except ImportError:
        print("Error: 'mcp' package is not installed.")
        print("Please install it using: pip install mcp")
