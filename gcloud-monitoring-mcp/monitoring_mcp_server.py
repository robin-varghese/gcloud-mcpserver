#!/usr/bin/env python3
"""
Google Cloud Monitoring MCP Server

This MCP server exposes Google Cloud Monitoring and Logging capabilities
as MCP tools for AI agents.
"""

import asyncio
import json
import sys
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from google.cloud import monitoring_v3, logging_v2
from google.api_core import datetime_helpers
from proto.marshal.collections.maps import MapComposite
from proto.marshal.collections.repeated import RepeatedComposite


# Initialize MCP server
app = Server("gcloud-monitoring-mcp")


def proto_to_dict(obj):
    """Recursively convert protobuf types to native Python types."""
    # Handle proto-plus MapComposite and RepeatedComposite
    if isinstance(obj, MapComposite):
        return {k: proto_to_dict(v) for k, v in obj.items()}
    if isinstance(obj, RepeatedComposite):
        return [proto_to_dict(v) for v in obj]
    
    # Handle any dict-like object (including ScalarMap, MessageMap, etc.)
    # Check if it has items() method and is not a plain dict
    if hasattr(obj, 'items') and not isinstance(obj, dict):
        try:
            return {k: proto_to_dict(v) for k, v in obj.items()}
        except (TypeError, AttributeError):
            pass
    
    # Handle any list-like object (including RepeatedScalarFieldContainer, etc.)
    # Check if it's iterable but not a string or dict
    if hasattr(obj, '__iter__') and not isinstance(obj, (str, dict, bytes)):
        try:
            return [proto_to_dict(v) for v in obj]
        except (TypeError, AttributeError):
            pass
    
    # Handle standard dict and list
    if isinstance(obj, dict):
        return {k: proto_to_dict(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [proto_to_dict(v) for v in obj]
    
    return obj


@app.list_tools()
async def list_tools() -> List[Tool]:
    """List available monitoring tools."""
    return [
        Tool(
            name="query_time_series",
            description="Query time series data from Cloud Monitoring. Returns metric values over a time period.",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_id": {
                        "type": "string",
                        "description": "GCP project ID"
                    },
                    "metric_type": {
                        "type": "string",
                        "description": "Metric type (e.g., 'compute.googleapis.com/instance/cpu/utilization')"
                    },
                    "resource_filter": {
                        "type": "string",
                        "description": "Optional resource filter (e.g., 'resource.instance_id=\"12345\"')",
                        "default": ""
                    },
                    "minutes_ago": {
                        "type": "integer",
                        "description": "How many minutes of historical data to fetch",
                        "default": 60
                    }
                },
                "required": ["project_id", "metric_type"]
            }
        ),
        Tool(
            name="query_logs",
            description="Query log entries from Cloud Logging. Returns matching log entries with full details.",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_id": {
                        "type": "string",
                        "description": "GCP project ID"
                    },
                    "filter": {
                        "type": "string",
                        "description": "Log filter query (e.g., 'resource.type=\"gce_instance\" AND severity>=ERROR'). Use empty string to get all logs."
                    },
                    "hours_ago": {
                        "type": "integer",
                        "description": "How many hours of historical logs to fetch",
                        "default": 24
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of log entries to return",
                        "default": 100
                    }
                },
                "required": ["project_id"]
            }
        ),
        Tool(
            name="list_metrics",
            description="List all available metric descriptors in a project.",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_id": {
                        "type": "string",
                        "description": "GCP project ID"
                    },
                    "filter": {
                        "type": "string",
                        "description": "Optional filter for metric types (e.g., 'metric.type = starts_with(\"compute.googleapis.com\")')",
                        "default": ""
                    }
                },
                "required": ["project_id"]
            }
        )
    ]


@app.call_tool()
async def call_tool(name: str, arguments: Any) -> List[TextContent]:
    """Handle tool calls."""
    try:
        if name == "query_time_series":
            result = await query_time_series(
                project_id=arguments["project_id"],
                metric_type=arguments["metric_type"],
                resource_filter=arguments.get("resource_filter", ""),
                minutes_ago=arguments.get("minutes_ago", 60)
            )
            return [TextContent(type="text", text=json.dumps(result, indent=2))]
        
        elif name == "query_logs":
            filter_val = arguments.get("filter", "")
            # Handle null/None values from JSON
            if filter_val is None:
                filter_val = ""
            result = await query_logs(
                project_id=arguments["project_id"],
                filter_str=filter_val,
                hours_ago=arguments.get("hours_ago", 24),
                limit=arguments.get("limit", 100)
            )
            return [TextContent(type="text", text=json.dumps(result, indent=2))]
        
        elif name == "list_metrics":
            result = await list_metrics_impl(
                project_id=arguments["project_id"],
                filter_str=arguments.get("filter", "")
            )
            return [TextContent(type="text", text=json.dumps(result, indent=2))]
        
        else:
            return [TextContent(type="text", text=f"Unknown tool: {name}")]
    
    except Exception as e:
        error_msg = f"Error executing {name}: {str(e)}"
        print(f"ERROR: {error_msg}", file=sys.stderr)
        return [TextContent(type="text", text=json.dumps({"error": error_msg}, indent=2))]


async def query_time_series(
    project_id: str,
    metric_type: str,
    resource_filter: str = "",
    minutes_ago: int = 60
) -> Dict[str, Any]:
    """Query time series data from Cloud Monitoring."""
    try:
        client = monitoring_v3.MetricServiceClient()
        project_name = f"projects/{project_id}"
        
        # Calculate time interval
        now = datetime.now(timezone.utc)
        end_time = now
        start_time = now - timedelta(minutes=minutes_ago)
        
        interval = monitoring_v3.TimeInterval({
            "end_time": end_time,
            "start_time": start_time
        })
        
        # Build filter
        filter_str = f'metric.type = "{metric_type}"'
        if resource_filter:
            filter_str += f" AND {resource_filter}"
        
        # Query time series
        results = client.list_time_series(
            request={
                "name": project_name,
                "filter": filter_str,
                "interval": interval,
                "view": monitoring_v3.ListTimeSeriesRequest.TimeSeriesView.FULL
            }
        )
        
        # Format results
        series_data = []
        for series in results:
            points_data = []
            for point in series.points:
                points_data.append({
                    "interval": {
                        "end_time": point.interval.end_time.isoformat(),
                        "start_time": point.interval.start_time.isoformat()
                    },
                    "value": {
                        "double_value": getattr(point.value, 'double_value', None),
                        "int64_value": getattr(point.value, 'int64_value', None)
                    }
                })
            
            series_data.append({
                "metric": dict(series.metric.labels),
                "resource": {
                    "type": series.resource.type,
                    "labels": dict(series.resource.labels)
                },
                "points": points_data
            })
        
        return {
            "time_series_count": len(series_data),
            "time_series": series_data
        }
    
    except Exception as e:
        return {"error": str(e)}



async def query_logs(
    project_id: str,
    filter_str: str,
    hours_ago: int = 24,
    limit: int = 100
) -> Dict[str, Any]:
    """Query log entries from Cloud Logging."""
    try:
        # Use the specific client class that we will import or access via the correct path
        from google.cloud.logging_v2.services.logging_service_v2 import LoggingServiceV2Client
        client = LoggingServiceV2Client()
        project_name = f"projects/{project_id}"
        
        # Query logs
        entries = client.list_log_entries(
            request={
                "resource_names": [project_name],
                "filter": filter_str,
                "order_by": "timestamp desc",
                "page_size": limit
            }
        )
        
        # Format results
        log_entries = []
        for entry in entries:
            log_entries.append({
                "log_name": entry.log_name,
                "resource": {
                    "type": entry.resource.type,
                    "labels": proto_to_dict(entry.resource.labels)
                },
                "timestamp": entry.timestamp.isoformat() if entry.timestamp else None,
                "severity": str(entry.severity),
                "text_payload": entry.text_payload if entry.text_payload else None,
                "json_payload": proto_to_dict(entry.json_payload) if entry.json_payload else None
            })
            
            # Respect limit
            if len(log_entries) >= limit:
                break
        
        return {
            "log_entry_count": len(log_entries),
            "log_entries": log_entries
        }
    
    except Exception as e:
        return {"error": str(e)}


async def list_metrics_impl(
    project_id: str,
    filter_str: str = ""
) -> Dict[str, Any]:
    """List all available metric descriptors."""
    try:
        client = monitoring_v3.MetricServiceClient()
        project_name = f"projects/{project_id}"
        
        # List metric descriptors
        descriptors = client.list_metric_descriptors(
            request={
                "name": project_name,
                "filter": filter_str
            }
        )
        
        # Format results
        metrics = []
        for descriptor in descriptors:
            metrics.append({
                "type": descriptor.type,
                "display_name": descriptor.display_name,
                "description": descriptor.description,
                "metric_kind": str(descriptor.metric_kind),
                "value_type": str(descriptor.value_type)
            })
        
        return {
            "metric_count": len(metrics),
            "metrics": metrics
        }
    
    except Exception as e:
        return {"error": str(e)}


async def main():
    """Main entry point for the MCP server."""
    print("Starting Google Cloud Monitoring MCP Server...", file=sys.stderr)
    
    async with stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            app.create_initialization_options()
        )


if __name__ == "__main__":
    asyncio.run(main())
