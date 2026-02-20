#!/usr/bin/env bash
# =============================================================================
# setup.sh – one-time host setup before running docker compose up
# Run as a user with sudo privileges on the DGX Spark
# =============================================================================
set -euo pipefail

# ── Load .env if present ──────────────────────────────────────────────────────
if [[ -f .env ]]; then
  # shellcheck disable=SC2046
  export $(grep -v '^#' .env | xargs)
fi

OLLAMA_DATA_PATH="${OLLAMA_DATA_PATH:-/data/ollama}"
WEBUI_DATA_PATH="${WEBUI_DATA_PATH:-/data/open-webui}"

echo "==> Creating data directories..."
sudo mkdir -p "$OLLAMA_DATA_PATH"
sudo mkdir -p "$WEBUI_DATA_PATH"

# Give the current user ownership so Docker bind-mounts work without root
sudo chown -R "$USER":"$USER" "$OLLAMA_DATA_PATH" "$WEBUI_DATA_PATH"
echo "    $OLLAMA_DATA_PATH"
echo "    $WEBUI_DATA_PATH"

# ── Verify NVIDIA Container Toolkit ──────────────────────────────────────────
echo ""
echo "==> Checking NVIDIA Container Toolkit..."
if ! docker info 2>/dev/null | grep -q "Runtimes.*nvidia"; then
  echo "[WARN] NVIDIA runtime not detected in Docker."
  echo "       Install the NVIDIA Container Toolkit before continuing:"
  echo "       https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html"
else
  echo "    NVIDIA runtime: OK"
fi

# ── Verify GPU visibility ─────────────────────────────────────────────────────
echo ""
echo "==> Detected GPUs:"
if command -v nvidia-smi &>/dev/null; then
  nvidia-smi --query-gpu=index,name,memory.total --format=csv,noheader
else
  echo "[WARN] nvidia-smi not found on PATH"
fi

echo ""
echo "==> Setup complete. Next steps:"
echo "    1. Copy .env.example to .env and update WEBUI_SECRET_KEY"
echo "    2. Run:  docker compose up -d"
echo "    3. Model downloads will run automatically (ollama-pull service)"
echo "    4. Open http://localhost:3000 once WebUI is healthy"
