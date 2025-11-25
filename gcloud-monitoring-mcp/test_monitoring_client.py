#!/usr/bin/env python3
"""
Test client for Google Cloud Monitoring MCP Server
"""

import asyncio
import os
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# Define the Docker command to run the monitoring MCP server
server_params = StdioServerParameters(
    command="docker",
    args=[
        "run",
        "-i",
        "--rm",
        "--network", "host",
        "-v", f"{os.path.expanduser('~')}/.config/gcloud:/root/.config/gcloud",
        "gcloud-monitoring-mcp-image"
    ],
    env=None
)

async def run_test():
    print("Starting Monitoring MCP Client...")
    print(f"Connecting to server via command: {server_params.command} {' '.join(server_params.args)}")
    
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            # Initialize the connection
            await session.initialize()
            print("\n--- Connected to Google Cloud Monitoring MCP Server ---")

            # List available tools
            print("\n[1] Listing Available Tools:")
            tools = await session.list_tools()
            for tool in tools.tools:
                print(f"  - {tool.name}: {tool.description[:70]}...")

            # Get project ID from user
            print("\n[2] Testing Monitoring Tools")
            project_id = input("Enter your GCP Project ID: ").strip()
            
            if not project_id:
                print("No project ID provided. Exiting.")
                return
            
            # Test list_metrics
            print(f"\n[3] Testing Tool: list_metrics (project: {project_id})")
            try:
                result = await session.call_tool(
                    "list_metrics",
                    arguments={
                        "project_id": project_id,
                        "filter": "metric.type = starts_with(\"compute.googleapis.com\")"
                    }
                )
                print("Result (first 5 metrics):")
                import json
                data = json.loads(result.content[0].text)
                if "error" in data:
                    print(f"  Error: {data['error']}")
                elif "metrics" in data:
                    for metric in data["metrics"][:5]:
                        print(f"  - {metric['type']}: {metric['display_name']}")
                    print(f"  ... and {data['metric_count'] - 5} more metrics")
                else:
                    print(f"  {data}")
            except Exception as e:
                print(f"Error calling list_metrics: {e}")
            
            # Test query_time_series (optional - only if user wants to continue)
            test_more = input("\nTest query_time_series for CPU metrics? (y/n): ").strip().lower()
            if test_more == 'y':
                instance_id = input("Enter VM instance ID (or press Enter to skip): ").strip()
                if instance_id:
                    print(f"\n[4] Testing Tool: query_time_series (instance: {instance_id})")
                    try:
                        result = await session.call_tool(
                            "query_time_series",
                            arguments={
                                "project_id": project_id,
                                "metric_type": "compute.googleapis.com/instance/cpu/utilization",
                                "resource_filter": f"resource.instance_id=\"{instance_id}\"",
                                "minutes_ago": 60
                            }
                        )
                        data = json.loads(result.content[0].text)
                        if "error" in data:
                            print(f"  Error: {data['error']}")
                        else:
                            print(f"  Found {data['time_series_count']} time series")
                            if data['time_series_count'] > 0:
                                for ts in data['time_series']:
                                    print(f"  Resource: {ts['resource']}")
                                    print(f"  Points: {len(ts['points'])}")
                                    if ts['points']:
                                        latest = ts['points'][0]
                                        value = latest['value']['double_value']
                                        if value is not None:
                                            print(f"  Latest CPU: {value * 100:.2f}%")
                    except Exception as e:
                        print(f"Error calling query_time_series: {e}")

if __name__ == "__main__":
    # Check if mcp is installed
    try:
        import mcp
        asyncio.run(run_test())
    except ImportError:
        print("Error: 'mcp' package is not installed.")
        print("Please install it using: pip install mcp")
