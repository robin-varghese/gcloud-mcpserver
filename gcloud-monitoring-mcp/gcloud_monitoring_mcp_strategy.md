# Strategy: Google Cloud Monitoring MCP Server in Docker

This document outlines the strategy to containerize and deploy a specialized Google Cloud Monitoring MCP server for use by AI agents. This server focuses exclusively on Google Cloud monitoring capabilities including metrics, logs, traces, and alerts.

## 1. Overview
The goal is to host a dedicated **Google Cloud Monitoring MCP server** within a Docker container. This allows an agentic application to query metrics, read logs, analyze traces, and manage alerts via the Model Context Protocol (MCP), with a consistent environment and isolated dependencies.

**Key Difference from GCloud MCP Server**: While the general `gcloud-mcp` server provides broad GCP functionality, this specialized server will focus on:
- Cloud Monitoring (Metrics & Time Series)
- Cloud Logging (Log entries & analytics)
- Cloud Trace (Distributed tracing)
- Error Reporting
- Alerting Policies

## 2. Prerequisites
Before building the server, ensure the following are prepared:

*   **Google Cloud Project**: A valid GCP project with **billing enabled**.
*   **gcloud CLI**: The gcloud CLI must be installed and **authenticated on the host machine**.
    *   **Authentication**: Run `gcloud auth login` to authenticate with your user account.
    *   **Default Project**: Set with `gcloud config set project PROJECT_ID`.
    *   **Verify**: Run `gcloud auth list` to confirm you're authenticated.
*   **User Permissions**: Your authenticated GCP user account must have appropriate IAM roles for monitoring:
    *   **Required**: `roles/monitoring.viewer` - Read access to metrics and time series
    *   **Required**: `roles/logging.viewer` - Read access to logs
    *   **Optional**: `roles/cloudtrace.user` - Access to trace data
    *   **Optional**: `roles/errorreporting.user` - Access to error reporting
    *   **For Writes**: `roles/monitoring.metricWriter` - If the server will write custom metrics
    *   **For Alerts**: `roles/monitoring.alertPolicyEditor` - If managing alert policies
*   **APIs Enabled**: Ensure the following APIs are enabled in your GCP project:
    *   Cloud Monitoring API (`monitoring.googleapis.com`)
    *   Cloud Logging API (`logging.googleapis.com`)
    *   Cloud Trace API (optional, `cloudtrace.googleapis.com`)
    *   Error Reporting API (optional, `clouderrorreporting.googleapis.com`)
*   **Docker**: Installed on the host machine.
*   **Node.js**: Version 20+ (required for the base image).
*   **Python 3**: Required for Google Cloud client libraries.

> **Note**: This strategy uses **host credential sharing** where the MCP server inherits the authenticated user's credentials from the host machine. This ensures that only users with proper GCP access can query monitoring data through the MCP server.

> **Alternative for Production**: For automated/production environments, you can use a service account instead. See the "Service Account Alternative" section at the end of this document.

## 3. Docker Image Strategy
The Docker image will bundle Node.js, Python, Google Cloud SDK with monitoring components, and the MCP server code.

### Dockerfile Specification
*   **Base Image**: `node:20-slim` (Lightweight, meets Node.js requirement).
*   **System Dependencies**:
    *   `python3` and `pip3` (Required for Google Cloud client libraries)
    *   `curl`, `gnupg`, `apt-transport-https`, `ca-certificates` (For installing gcloud CLI)
*   **Google Cloud SDK**:
    *   Add Google Cloud SDK repository
    *   Install `google-cloud-cli` base package
    *   **CRITICAL**: Install monitoring-specific components:
        *   `google-cloud-cli-monitoring` - For `gcloud monitoring` commands
        *   `google-cloud-cli-log-streaming` - For log streaming capabilities
*   **Python Client Libraries**:
    *   Install Google Cloud client libraries for programmatic access:
        *   `google-cloud-monitoring` - For Monitoring API
        *   `google-cloud-logging` - For Logging API
        *   `google-cloud-trace` (optional) - For Trace API
        *   `google-cloud-error-reporting` (optional) - For Error Reporting API
*   **MCP Server Implementation**:
    *   **Option A: Custom Implementation** - Build a custom Node.js MCP server that:
        *   Exposes monitoring-specific tools
        *   Uses `exec` to call `gcloud monitoring` commands
        *   Parses and returns structured data
    *   **Option B: Python-based** - Build a Python MCP server using:
        *   `mcp` Python SDK
        *   Google Cloud client libraries directly
        *   More efficient for complex queries
*   **Authentication**:
    *   The container will use the host's gcloud configuration via volume mount
    *   No service account activation needed
*   **Entrypoint**:
    *   The container executes the MCP server on startup

### Complete Dockerfile Example (Node.js + gcloud monitoring)
```dockerfile
FROM node:20-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    gnupg \
    apt-transport-https \
    ca-certificates \
    python3 \
    python3-pip \
    && rm -rf /var/lib/apt/lists/*

# Install Google Cloud SDK with monitoring components
RUN echo "deb [signed-by=/usr/share/keyrings/cloud.google.gpg] https://packages.cloud.google.com/apt cloud-sdk main" | \
    tee -a /etc/apt/sources.list.d/google-cloud-sdk.list && \
    curl https://packages.cloud.google.com/apt/doc/apt-key.gpg | \
    gpg --dearmor -o /usr/share/keyrings/cloud.google.gpg && \
    apt-get update && \
    apt-get install -y \
        google-cloud-cli \
        google-cloud-cli-monitoring \
        google-cloud-cli-log-streaming && \
    rm -rf /var/lib/apt/lists/*

# Install Python Google Cloud client libraries
RUN pip3 install --no-cache-dir \
    google-cloud-monitoring \
    google-cloud-logging \
    google-cloud-trace \
    google-cloud-error-reporting

# Create app directory
WORKDIR /app

# Copy MCP server code (to be implemented)
COPY monitoring-mcp-server.js /app/

# Set entrypoint to run MCP server
# Credentials will be inherited from host via volume mount
ENTRYPOINT ["node", "/app/monitoring-mcp-server.js"]
```

### Alternative: Python-based Dockerfile
```dockerfile
FROM python:3.11-slim

# Install Node.js (for npx if needed)
RUN apt-get update && apt-get install -y \
    curl \
    gnupg \
    apt-transport-https \
    ca-certificates \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# Install Google Cloud SDK with monitoring components
RUN echo "deb [signed-by=/usr/share/keyrings/cloud.google.gpg] https://packages.cloud.google.com/apt cloud-sdk main" | \
    tee -a /etc/apt/sources.list.d/google-cloud-sdk.list && \
    curl https://packages.cloud.google.com/apt/doc/apt-key.gpg | \
    gpg --dearmor -o /usr/share/keyrings/cloud.google.gpg && \
    apt-get update && \
    apt-get install -y \
        google-cloud-cli \
        google-cloud-cli-monitoring \
        google-cloud-cli-log-streaming && \
    rm -rf /var/lib/apt/lists/*

# Install Python dependencies
RUN pip install --no-cache-dir \
    mcp \
    google-cloud-monitoring \
    google-cloud-logging \
    google-cloud-trace \
    google-cloud-error-reporting

# Create app directory
WORKDIR /app

# Copy MCP server code (to be implemented)
COPY monitoring_mcp_server.py /app/

# Set entrypoint
ENTRYPOINT ["python", "/app/monitoring_mcp_server.py"]
```

## 4. Authorization Strategy
Security is handled at two levels:

### A. Server Identity (GCP Auth)
The MCP server authenticates with Google Cloud using **host credential sharing**.

*   **Mechanism**: The container mounts the host's `~/.config/gcloud` directory.
*   **How it works**:
    1. User runs `gcloud auth login` on the host machine
    2. gcloud stores credentials in `~/.config/gcloud`
    3. Docker container mounts this directory and inherits the credentials
    4. All API calls use the authenticated user's identity
*   **Access Control**: Only users who have authenticated with `gcloud auth login` can use the MCP server. The user's GCP IAM permissions determine what monitoring data they can access.
*   **Benefits**:
    *   No service account keys to manage
    *   Automatic access control based on user identity
    *   Credentials never leave the host machine
    *   Follows the principle of least privilege (user's actual permissions)

### B. Client-Server Authorization (MCP Auth)
*   **Local/Stdio (Recommended)**:
    *   The agent spawns the Docker container directly (e.g., `docker run -i ...`)
    *   Authentication is implicit via access to the host's Docker daemon
    *   Communication happens over Stdio (Standard Input/Output)
    *   This is the approach used in this strategy
*   **Remote/HTTP (Advanced)**:
    *   If hosting as a remote web service (SSE), implement **OAuth 2.1** as per MCP specs
    *   This requires a wrapper around the server to handle the auth handshake
    *   Not covered in this strategy (use Stdio + Docker for simplicity)

## 5. Connection Strategy
How the agent connects to the Dockerized MCP server.

### Configuration
In your agent's MCP configuration (e.g., `claude_desktop_config.json` or custom agent config):

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

**Important flags explained**:
*   `-i`: Keeps stdin open (crucial for MCP stdio communication)
*   `--rm`: Cleans up container after exit
*   `--network host`: Allows the container to access Google Cloud APIs
*   `-v $HOME/.config/gcloud:/root/.config/gcloud`: Mounts the host's gcloud configuration directory
    *   This shares your authenticated credentials with the container
    *   **Note**: Must be read-write (default) because gcloud writes logs and lock files
    *   On **macOS/Linux**: Use `$HOME/.config/gcloud`
    *   On **Windows**: Use `%APPDATA%\gcloud` instead

> **Security Note**: The container inherits the authenticated user's credentials. Only users who have run `gcloud auth login` on the host machine can use the MCP server.

## 6. MCP Server Implementation Strategy

### Recommended Tools to Expose

The monitoring MCP server should expose the following tools:

#### Metrics & Time Series
- `list_metrics` - List available metric types in the project
- `get_metric_descriptor` - Get details about a specific metric
- `query_time_series` - Query time series data with filters
- `get_latest_metric_value` - Get the most recent value for a metric
- `aggregate_metrics` - Aggregate metrics across resources

#### Logging
- `list_logs` - List available log names
- `query_logs` - Query log entries with filters
- `get_recent_logs` - Get recent log entries for a resource
- `search_logs_by_text` - Full-text search in logs
- `tail_logs` - Stream real-time log entries

#### Tracing (Optional)
- `list_traces` - List trace data
- `get_trace_details` - Get detailed span information
- `analyze_trace_latency` - Analyze latency distribution

#### Error Reporting (Optional)
- `list_error_groups` - List error groups
- `get_error_details` - Get details for specific errors
- `get_error_statistics` - Get error frequency stats

#### Alerting
- `list_alert_policies` - List alert policies
- `get_alert_policy` - Get alert policy details
- `check_alert_status` - Check if alerts are firing

### Implementation Approaches

**Approach 1: Shell Command Wrapper (Simpler)**
- Use Node.js `child_process.exec` to call `gcloud monitoring` commands
- Parse JSON output and return via MCP
- Pros: Simpler, leverages existing gcloud commands
- Cons: Limited by gcloud CLI capabilities, slower

**Approach 2: Direct API Client (More Powerful)**
- Use Python `google-cloud-monitoring` library
- Call Monitoring/Logging APIs directly
- Pros: More flexible, faster, fuller API access
- Cons: More complex implementation

**Recommended**: Use **Approach 2 (Python)** for better performance and flexibility.

## 7. Testing & Debugging
Use the **MCP Inspector** to verify the server before integrating with the agent.

*   **Command**:
    ```bash
    npx @modelcontextprotocol/inspector docker run -i --rm \
      --network host \
      -v $HOME/.config/gcloud:/root/.config/gcloud \
      gcloud-monitoring-mcp-image
    ```
*   **Verification**:
    *   The Inspector will launch a web UI (usually at `http://localhost:5173`)
    *   Verify that tools like `query_time_series` or `query_logs` appear in the Tools tab
    *   Test a tool call (e.g., query recent CPU metrics) and check the output
    *   Check the Notifications pane for any errors or warnings
    *   If you see authentication errors, verify that `gcloud auth list` shows an active account on your host machine

## 8. Implementation Steps

### Step 1: Authenticate with GCloud
```bash
# Authenticate with your GCP user account
gcloud auth login

# Set your default project
gcloud config set project YOUR_PROJECT_ID

# Verify authentication
gcloud auth list
# You should see your account marked as ACTIVE

# Enable required APIs
gcloud services enable monitoring.googleapis.com
gcloud services enable logging.googleapis.com
gcloud services enable cloudtrace.googleapis.com
gcloud services enable clouderrorreporting.googleapis.com
```

### Step 2: Implement MCP Server Code
Create the MCP server implementation file (`monitoring_mcp_server.py` or `monitoring-mcp-server.js`).

**Example structure for Python implementation**:
```python
from mcp import ClientSession, StdioServerParameters
from google.cloud import monitoring_v3, logging_v2
import asyncio

# Define MCP tools
async def query_time_series(project_id, metric_filter, start_time, end_time):
    """Query metrics from Cloud Monitoring"""
    client = monitoring_v3.MetricServiceClient()
    # Implementation here
    pass

async def query_logs(project_id, log_filter, limit=100):
    """Query logs from Cloud Logging"""
    client = logging_v2.LoggingServiceV2Client()
    # Implementation here
    pass

# MCP server setup and tool registration
# ... (full implementation details)
```

### Step 3: Build Docker Image
```bash
# Create Dockerfile (use the complete example from Section 3)
# Then build the image
docker build -t gcloud-monitoring-mcp-image .

# Verify the image was created
docker images | grep gcloud-monitoring-mcp-image

# Test gcloud monitoring commands are available
docker run --rm gcloud-monitoring-mcp-image gcloud monitoring metrics-descriptors list --limit=1
```

### Step 4: Test with MCP Inspector
```bash
npx @modelcontextprotocol/inspector docker run -i --rm \
  --network host \
  -v $HOME/.config/gcloud:/root/.config/gcloud \
  gcloud-monitoring-mcp-image
```

The Inspector will launch a web UI where you can:
*   View all available monitoring tools
*   Test tool calls interactively (e.g., query CPU metrics)
*   Inspect request/response payloads
*   Verify that your host credentials are working

### Step 5: Configure Your Agent
Add the configuration from Section 5 to your agent's MCP settings file.

### Step 6: Verify Available Tools
Once connected, your agent should have access to monitoring-specific tools such as:

**Metrics Tools**:
- `query_time_series` - Query metric time series with custom filters
- `get_latest_metric_value` - Get current value for a specific metric
- `list_metrics` - List all available metrics in the project

**Logging Tools**:
- `query_logs` - Query log entries with filters and time ranges
- `tail_logs` - Stream real-time logs
- `search_logs` - Full-text search across logs

**Alerting Tools**:
- `list_alert_policies` - List configured alert policies
- `check_alert_status` - Check if any alerts are currently firing

## 9. Example Use Cases

### Use Case 1: Monitor VM CPU Usage
```
Agent: "What's the CPU utilization of instance-1 over the last hour?"
Tool: query_time_series(
  metric="compute.googleapis.com/instance/cpu/utilization",
  resource_filter='resource.instance_id="12345"',
  start_time="-1h",
  end_time="now"
)
```

### Use Case 2: Investigate Application Errors
```
Agent: "Show me recent errors in my application logs"
Tool: query_logs(
  log_filter='severity>=ERROR AND resource.type="gae_app"',
  time_range="last_24h",
  limit=50
)
```

### Use Case 3: Check Alert Status
```
Agent: "Are there any firing alerts in my project?"
Tool: check_alert_status()
```

---

## Appendix: Service Account Alternative (For Production/Automation)

If you need to use a **service account** instead of host credentials (e.g., for CI/CD pipelines, automated systems), follow this alternative approach:

### Prerequisites
*   Create a GCP Service Account with appropriate monitoring roles:
    *   `roles/monitoring.viewer`
    *   `roles/logging.viewer`
    *   `roles/cloudtrace.user` (optional)
*   Generate a JSON key file for the service account

### Modified Configuration
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
        "-v", "/path/to/gcp-sa-key.json:/app/gcp-key.json",
        "-e", "GOOGLE_APPLICATION_CREDENTIALS=/app/gcp-key.json",
        "-e", "GCP_PROJECT_ID=your-project-id",
        "gcloud-monitoring-mcp-image"
      ]
    }
  }
}
```

### Service Account Setup Commands
```bash
# Create service account
gcloud iam service-accounts create monitoring-mcp-sa \
  --display-name="Monitoring MCP Server Service Account"

# Grant monitoring viewer role
gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
  --member="serviceAccount:monitoring-mcp-sa@YOUR_PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/monitoring.viewer"

# Grant logging viewer role
gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
  --member="serviceAccount:monitoring-mcp-sa@YOUR_PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/logging.viewer"

# Generate key file
gcloud iam service-accounts keys create gcp-monitoring-key.json \
  --iam-account=monitoring-mcp-sa@YOUR_PROJECT_ID.iam.gserviceaccount.com
```

### Trade-offs
**Service Account Approach**:
- ✅ Works in automated/headless environments
- ✅ Consistent identity across different users
- ❌ Requires key file management
- ❌ Less secure (keys can be compromised)
- ❌ No automatic user-based access control

**Host Credential Sharing (Recommended)**:
- ✅ No key files to manage
- ✅ Automatic access control based on user identity
- ✅ More secure (credentials never leave host)
- ✅ Follows principle of least privilege
- ❌ Requires user to be authenticated on host
- ❌ Not suitable for automated systems
