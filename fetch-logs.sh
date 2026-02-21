#!/usr/bin/env bash
# fetch-logs.sh — Fetch Docker container logs from a remote host and save locally.
#
# Usage:
#   ./fetch-logs.sh <ssh_user> <remote_host> <container_name> [output_file]
#
# Arguments:
#   ssh_user        SSH username on the remote machine
#   remote_host     Hostname or IP address of the remote machine
#   container_name  Name or ID of the Docker container
#   output_file     (optional) Local file to write logs to
#                   Defaults to: <container_name>-<timestamp>.log
#
# Examples:
#   ./fetch-logs.sh username spark_ip_addr ollama
#   ./fetch-logs.sh username spark_ip_addr open-webui ./webui.log
#
# Requirements:
#   - SSH key-based auth configured for the remote host
#   - Remote user must be in the docker group (or have sudo docker access)

set -euo pipefail

# ---------------------------------------------------------------------------
# Usage
# ---------------------------------------------------------------------------
usage() {
  echo "Usage: $0 <ssh_user> <remote_host> <container_name> [output_file]" >&2
  exit 1
}

[[ $# -lt 3 || $# -gt 4 ]] && usage

SSH_USER="$1"
REMOTE_HOST="$2"
CONTAINER="$3"
TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
OUTPUT_FILE="${4:-${CONTAINER}-${TIMESTAMP}.log}"

# ---------------------------------------------------------------------------
# Verify SSH connectivity
# ---------------------------------------------------------------------------
echo "Connecting to ${SSH_USER}@${REMOTE_HOST} ..."
if ! ssh -q -o BatchMode=yes -o ConnectTimeout=5 "${SSH_USER}@${REMOTE_HOST}" exit 2>/dev/null; then
  echo "Error: Cannot reach ${SSH_USER}@${REMOTE_HOST} — check hostname, SSH keys, and network." >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# Verify the container exists on the remote host
# ---------------------------------------------------------------------------
if ! ssh -q "${SSH_USER}@${REMOTE_HOST}" "docker inspect --format '{{.Name}}' '${CONTAINER}'" &>/dev/null; then
  echo "Error: Container '${CONTAINER}' not found on ${REMOTE_HOST}." >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# Fetch logs
# ---------------------------------------------------------------------------
echo "Fetching logs for '${CONTAINER}' from ${REMOTE_HOST} ..."
ssh "${SSH_USER}@${REMOTE_HOST}" "docker logs --timestamps '${CONTAINER}'" > "${OUTPUT_FILE}" 2>&1

echo "Saved to: ${OUTPUT_FILE} ($(wc -l < "${OUTPUT_FILE}") lines)"
