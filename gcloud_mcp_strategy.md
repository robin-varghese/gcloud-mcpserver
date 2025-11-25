# Strategy: GCloud MCP Server in Docker

This document outlines the strategy to containerize and deploy the Google Cloud MCP server (`googleapis/gcloud-mcp`) for use by AI agents.

## 1. Overview
The goal is to host the `gcloud-mcp` server within a Docker container. This allows an agentic application to perform Google Cloud operations (e.g., listing buckets, managing VMs) via the Model Context Protocol (MCP), with a consistent environment and isolated dependencies.

## 2. Prerequisites
Before building the server, ensure the following are prepared:

*   **Google Cloud Project**: A valid GCP project with **billing enabled**.
*   **gcloud CLI**: The gcloud CLI must be installed and **authenticated on the host machine**.
    *   **Authentication**: Run `gcloud auth login` to authenticate with your user account.
    *   **Default Project**: Set with `gcloud config set project PROJECT_ID`.
    *   **Verify**: Run `gcloud auth list` to confirm you're authenticated.
*   **User Permissions**: Your authenticated GCP user account must have appropriate IAM roles:
    *   Example: `roles/storage.objectViewer` for reading GCS buckets.
    *   Example: `roles/compute.viewer` for listing VM instances.
    *   Example: `roles/logging.viewer` for observability tools.
    *   **Admin rights** are recommended for full gcloud command access.
*   **Docker**: Installed on the host machine.
*   **Node.js**: Version 20+ (required for the base image).

> **Note**: This strategy uses **host credential sharing** where the MCP server inherits the authenticated user's credentials from the host machine. This ensures that only users with proper GCP access can execute gcloud commands through the MCP server.

> **Alternative for Production**: For automated/production environments, you can use a service account instead. See the "Service Account Alternative" section at the end of this document.

## 3. Docker Image Strategy
The Docker image will bundle Node.js, the Google Cloud CLI (`gcloud`), and the MCP server code.

### Dockerfile Specification
*   **Base Image**: `node:20-slim` (Lightweight, meets version requirement).
*   **System Dependencies**:
    *   `python3` (Required by gcloud CLI).
    *   `curl`, `gnupg`, `apt-transport-https`, `ca-certificates` (For installing gcloud CLI).
*   **Google Cloud SDK**:
    *   Add Google Cloud SDK repository.
    *   Install the `google-cloud-cli` package via apt-get (Debian-based install).
*   **MCP Server**:
    *   The official package name is **`@google-cloud/gcloud-mcp`** (published on npm).
    *   No need to pre-install; `npx` will fetch it on demand.
*   **Authentication**:
    *   The container will use the host's gcloud configuration via volume mount.
    *   No service account activation needed.
*   **Entrypoint**:
    *   The container executes the MCP server directly.
    *   Command: `npx -y @google-cloud/gcloud-mcp`

### Complete Dockerfile Example
```dockerfile
FROM node:20-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    gnupg \
    apt-transport-https \
    ca-certificates \
    python3 \
    && rm -rf /var/lib/apt/lists/*

# Install Google Cloud SDK
RUN echo "deb [signed-by=/usr/share/keyrings/cloud.google.gpg] https://packages.cloud.google.com/apt cloud-sdk main" | \
    tee -a /etc/apt/sources.list.d/google-cloud-sdk.list && \
    curl https://packages.cloud.google.com/apt/doc/apt-key.gpg | \
    gpg --dearmor -o /usr/share/keyrings/cloud.google.gpg && \
    apt-get update && apt-get install -y google-cloud-cli && \
    rm -rf /var/lib/apt/lists/*

# Create app directory
WORKDIR /app

# Set entrypoint to run MCP server directly
# Credentials will be inherited from host via volume mount
ENTRYPOINT ["npx", "-y", "@google-cloud/gcloud-mcp"]
```


## 4. Authorization Strategy
Security is handled at two levels:

### A. Server Identity (GCP Auth)
The MCP server authenticates with Google Cloud using **host credential sharing**.

*   **Mechanism**: The container mounts the host's `~/.config/gcloud` directory (read-only).
*   **How it works**:
    1. User runs `gcloud auth login` on the host machine.
    2. gcloud stores credentials in `~/.config/gcloud`.
    3. Docker container mounts this directory and inherits the credentials.
    4. All gcloud commands executed by the MCP server use the authenticated user's identity.
*   **Access Control**: Only users who have authenticated with `gcloud auth login` can use the MCP server. The user's GCP IAM permissions determine what operations are allowed.
*   **Benefits**:
    *   No service account keys to manage
    *   Automatic access control based on user identity
    *   Credentials never leave the host machine
    *   Follows the principle of least privilege (user's actual permissions)

### B. Client-Server Authorization (MCP Auth)
*   **Local/Stdio (Recommended)**:
    *   The agent spawns the Docker container directly (e.g., `docker run -i ...`).
    *   Authentication is implicit via access to the host's Docker daemon.
    *   Communication happens over Stdio (Standard Input/Output).
    *   This is the approach used in this strategy.
*   **Remote/HTTP (Advanced)**:
    *   If hosting as a remote web service (SSE), implement **OAuth 2.1** as per MCP specs.
    *   This requires a wrapper around the server to handle the auth handshake before passing messages to the MCP handler.
    *   Not covered in this strategy (use Stdio + Docker for simplicity).

## 5. Connection Strategy
How the agent connects to the Dockerized MCP server.

### Configuration
In your agent's MCP configuration (e.g., `claude_desktop_config.json` or custom agent config):

```json
{
  "mcpServers": {
    "gcloud": {
      "command": "docker",
      "args": [
        "run",
        "-i",
        "--rm",
        "--network", "host",
        "-v", "$HOME/.config/gcloud:/root/.config/gcloud",
        "gcloud-mcp-image"
      ]
    }
  }
}
```

**Important flags explained**:
*   `-i`: Keeps stdin open (crucial for MCP stdio communication).
*   `--rm`: Cleans up container after exit.
*   `--network host`: Allows the container to access Google Cloud APIs.
*   `-v $HOME/.config/gcloud:/root/.config/gcloud`: Mounts the host's gcloud configuration directory into the container.
    *   This shares your authenticated credentials with the container.
    *   **Note**: Must be read-write (default) because gcloud writes logs and lock files.
    *   On **macOS/Linux**: Use `$HOME/.config/gcloud`
    *   On **Windows**: Use `%APPDATA%\gcloud` instead

> **Security Note**: The container inherits the authenticated user's credentials. Only users who have run `gcloud auth login` on the host machine can use the MCP server. This provides automatic access control based on GCP IAM permissions.

## 6. Testing & Debugging
Use the **MCP Inspector** to verify the server before integrating with the agent.

*   **Command**:
    ```bash
    npx @modelcontextprotocol/inspector docker run -i --rm \
      --network host \
      -v $HOME/.config/gcloud:/root/.config/gcloud \
      gcloud-mcp-image
    ```
*   **Verification**:
    *   The Inspector will launch a web UI (usually at `http://localhost:5173`).
    *   Verify that tools like `list_buckets` or `run_gcloud_command` appear in the Tools tab.
    *   Test a tool call (e.g., list buckets) and check the output.
    *   Check the Notifications pane for any errors or warnings.
    *   If you see authentication errors, verify that `gcloud auth list` shows an active account on your host machine.


## 7. Implementation Steps

### Step 1: Authenticate with GCloud
```bash
# Authenticate with your GCP user account
gcloud auth login

# Set your default project
gcloud config set project YOUR_PROJECT_ID

# Verify authentication
gcloud auth list
# You should see your account marked as ACTIVE

# Test that you can access GCP resources
gcloud projects describe YOUR_PROJECT_ID
```

### Step 2: Build Docker Image
```bash
# Create Dockerfile (use the complete example from Section 3)
# Then build the image
docker build -t gcloud-mcp-image .

# Verify the image was created
docker images | grep gcloud-mcp-image
```

### Step 3: Test with MCP Inspector
```bash
npx @modelcontextprotocol/inspector docker run -i --rm \
  --network host \
  -v $HOME/.config/gcloud:/root/.config/gcloud \
  gcloud-mcp-image
```

The Inspector will launch a web UI where you can:
*   View all available tools
*   Test tool calls interactively
*   Inspect request/response payloads
*   Verify that your host credentials are working

### Step 4: Configure Your Agent
Add the configuration from Section 5 to your agent's MCP settings file (e.g., `claude_desktop_config.json`, `.cursor/mcp.json`, or `.gemini/settings.json`).

### Step 5: Verify Available Tools
Once connected, your agent should have access to these tools:

**Core Tools**:
- `run_gcloud_command` - Execute any gcloud command
- `list_buckets` - List GCS buckets
- `list_objects` - List objects in a bucket
- `read_object_content` - Read object content
- `write_object` - Write to an object
- `delete_object` - Delete an object

**Observability Tools**:
- `list_log_entries` - Query Cloud Logging
- `list_log_names` - List available logs
- `list_metric_descriptors` - List metrics
- `list_time_series` - Query time series data
- `list_traces` - List Cloud Trace data

**Storage Insights**:
- `get_metadata_table_schema` - Get BigQuery schema
- `execute_insights_query` - Run insights queries

For the complete list, see the [official documentation](https://github.com/googleapis/gcloud-mcp).

---

## Appendix: Service Account Alternative (For Production/Automation)

If you need to use a **service account** instead of host credentials (e.g., for CI/CD pipelines, automated systems, or environments where user authentication isn't available), follow this alternative approach:

### Prerequisites
*   Create a GCP Service Account with appropriate roles
*   Generate a JSON key file for the service account

### Modified Dockerfile
Add an entrypoint script that activates the service account:

```dockerfile
FROM node:20-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    gnupg \
    apt-transport-https \
    ca-certificates \
    python3 \
    && rm -rf /var/lib/apt/lists/*

# Install Google Cloud SDK
RUN echo "deb [signed-by=/usr/share/keyrings/cloud.google.gpg] https://packages.cloud.google.com/apt cloud-sdk main" | \
    tee -a /etc/apt/sources.list.d/google-cloud-sdk.list && \
    curl https://packages.cloud.google.com/apt/doc/apt-key.gpg | \
    gpg --dearmor -o /usr/share/keyrings/cloud.google.gpg && \
    apt-get update && apt-get install -y google-cloud-cli && \
    rm -rf /var/lib/apt/lists/*

# Create app directory
WORKDIR /app

# Create entrypoint script that activates service account
RUN echo '#!/bin/bash\n\
set -e\n\
if [ -f "$GOOGLE_APPLICATION_CREDENTIALS" ]; then\n\
  echo "Activating service account..."\n\
  gcloud auth activate-service-account --key-file="$GOOGLE_APPLICATION_CREDENTIALS"\n\
  gcloud config set project "$GCP_PROJECT_ID"\n\
fi\n\
exec npx -y @google-cloud/gcloud-mcp' > /app/entrypoint.sh && \
    chmod +x /app/entrypoint.sh

# Set entrypoint
ENTRYPOINT ["/app/entrypoint.sh"]
```

### Modified Configuration
```json
{
  "mcpServers": {
    "gcloud": {
      "command": "docker",
      "args": [
        "run",
        "-i",
        "--rm",
        "--network", "host",
        "-v", "/path/to/gcp-sa-key.json:/app/gcp-key.json",
        "-e", "GOOGLE_APPLICATION_CREDENTIALS=/app/gcp-key.json",
        "-e", "GCP_PROJECT_ID=your-project-id",
        "gcloud-mcp-image"
      ]
    }
  }
}
```

### Service Account Setup Commands
```bash
# Create service account
gcloud iam service-accounts create mcp-server-sa \
  --display-name="MCP Server Service Account"

# Grant necessary roles
gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
  --member="serviceAccount:mcp-server-sa@YOUR_PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/storage.objectViewer"

# Generate key file
gcloud iam service-accounts keys create gcp-sa-key.json \
  --iam-account=mcp-server-sa@YOUR_PROJECT_ID.iam.gserviceaccount.com
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
