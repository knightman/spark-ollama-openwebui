#!/usr/bin/env bash
# deploy.sh — sync this project to the DGX Spark over SSH
#
# Copies every git-tracked file plus .env to the remote directory defined in .env.
# Requires: rsync, SSH access to the Spark (key-based auth recommended).
# Configure SPARK_SSH_USER, SPARK_SSH_HOST, SPARK_DEPLOY_DIR in your .env.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ── Load .env ──────────────────────────────────────────────────────────────────
if [[ ! -f "$SCRIPT_DIR/.env" ]]; then
  echo "ERROR: .env not found." >&2
  echo "       Copy .env.example to .env and set SPARK_SSH_USER, SPARK_SSH_HOST, SPARK_DEPLOY_DIR" >&2
  exit 1
fi
# shellcheck source=.env
source "$SCRIPT_DIR/.env"

# ── Validate required deploy variables ────────────────────────────────────────
missing=()
for var in SPARK_SSH_USER SPARK_SSH_HOST SPARK_DEPLOY_DIR; do
  [[ -z "${!var:-}" ]] && missing+=("$var")
done
if [[ ${#missing[@]} -gt 0 ]]; then
  echo "ERROR: missing required variable(s) in .env: ${missing[*]}" >&2
  exit 1
fi

REMOTE="${SPARK_SSH_USER}@${SPARK_SSH_HOST}"

echo "Deploying to ${REMOTE}:${SPARK_DEPLOY_DIR} ..."
echo ""

# ── Ensure remote directory exists ────────────────────────────────────────────
ssh "$REMOTE" "mkdir -p ${SPARK_DEPLOY_DIR}"

# ── Rsync git-tracked files + .env ────────────────────────────────────────────
cd "$SCRIPT_DIR"
{ git ls-files; echo ".env"; } \
  | rsync -avz --files-from=- . "${REMOTE}:${SPARK_DEPLOY_DIR}/"

echo ""
echo "Done. Stack files are at ${REMOTE}:${SPARK_DEPLOY_DIR}"
echo ""
echo "To start (or restart) the stack on the Spark:"
echo "  ssh ${REMOTE} 'cd ${SPARK_DEPLOY_DIR} && docker compose up -d'"
