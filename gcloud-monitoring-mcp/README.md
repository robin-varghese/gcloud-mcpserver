# Google Cloud Monitoring MCP Server

A Model Context Protocol (MCP) server that exposes Google Cloud Monitoring and Logging capabilities to AI agents.

## Features

### Available Tools

1. **query_time_series** - Query metrics from Cloud Monitoring
   - Get CPU, memory, network, and other metric values
   - Supports custom time ranges and resource filters
   
2. **query_logs** - Query log entries from Cloud Logging
   - Search logs with filters (severity, resource type, etc.)
   - Supports custom time ranges and limits

3. **list_metrics** - List all available metric descriptors
   - Discover what metrics are available in your project
   - Filter by metric type prefix

## Prerequisites

- Docker installed and running
- gcloud CLI authenticated: `gcloud auth login`
- GCP project with Cloud Monitoring and Logging APIs enabled
- Appropriate IAM permissions:
  - `roles/monitoring.viewer` - Read metrics
  - `roles/logging.viewer` - Read logs

## Quick Start

### 1. Build the Docker Image

```bash
cd gcloud-monitoring-mcp
docker build -t gcloud-monitoring-mcp-image .
```

### 2. Test with MCP Inspector

```bash
npx @modelcontextprotocol/inspector docker run -i --rm \
  --network host \
  -v $HOME/.config/gcloud:/root/.config/gcloud \
  gcloud-monitoring-mcp-image
```

This will launch a web UI at `http://localhost:5173` where you can test the tools interactively.

### 3. Configure Your AI Agent

Add this configuration to your agent's MCP settings file (e.g., `claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "gcloud-monitoring": {
      "command": "docker",
      "args": [
        "run",
        "-i",
        "--rm",
        "--network", "host",
        "-v", "$HOME/.config/gcloud:/root/.config/gcloud",
        "gcloud-monitoring-mcp-image"
      ]
    }
  }
}
```

## Example Tool Calls

### List Available Metrics

```json
{
  "tool": "list_metrics",
  "arguments": {
    "project_id": "your-project-id",
    "filter": "metric.type = starts_with(\"compute.googleapis.com\")"
  }
}
```

### Query CPU Utilization

```json
{
  "tool": "query_time_series",
  "arguments": {
    "project_id": "your-project-id",
    "metric_type": "compute.googleapis.com/instance/cpu/utilization",
    "resource_filter": "resource.instance_id=\"12345\"",
    "minutes_ago": 60
  }
}
```

### Query Error Logs

```json
{
  "tool": "query_logs",
  "arguments": {
    "project_id": "your-project-id",
    "filter": "severity>=ERROR",
    "hours_ago": 24,
    "limit": 50
  }
}
```

## Authentication

This server uses **host credential sharing**:
- It mounts your local `~/.config/gcloud` directory into the container
- Uses your authenticated user credentials
- Respects your GCP IAM permissions
- No service account keys required

## Troubleshooting

### "Permission Denied" Errors
Ensure your user account has the required IAM roles:
```bash
gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
  --member="user:your-email@example.com" \
  --role="roles/monitoring.viewer"
```

### "API Not Enabled" Errors
Enable the required APIs:
```bash
gcloud services enable monitoring.googleapis.com
gcloud services enable logging.googleapis.com
```

### No Data Returned
- Check that resources exist in your project
- Verify the time range includes when the resources were running
- Confirm your filter syntax is correct

## Architecture

- **Base Image**: `python:3.11-slim`
- **Components**:
  - Python MCP SDK (`mcp`)
  - Google Cloud Monitoring client (`google-cloud-monitoring`)
  - Google Cloud Logging client (`google-cloud-logging`)
  - Google Cloud SDK with monitoring CLI tools
- **Communication**: Stdio (Standard Input/Output)
- **Authentication**: Host credential sharing via volume mount

## Related

For general Google Cloud operations (compute, storage, etc.), see the companion [gcloud-mcp](../README.md) server.
