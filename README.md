# Ollama + Open WebUI on NVIDIA DGX Spark

A self-hosted, GPU-accelerated stack for running context-aware multimodal LLMs.
Ollama runs as the inference backend on a **DGX Spark**; you interact with it from a **dev laptop** via Open WebUI in a browser or via Claude Code over MCP.

```
Dev laptop  ──MCP (port 11434)──►  DGX Spark: Ollama
Dev laptop  ──HTTP (port 3000)──►  DGX Spark: Open WebUI
```

---

## File inventory

| File | Purpose | Runs on |
|---|---|---|
| `docker-compose.yml` | Full service definition (Ollama, model puller, Open WebUI) | DGX Spark |
| `.env.example` | Template for environment variables | DGX Spark |
| `.env` | Your local environment overrides (not committed) | DGX Spark |
| `setup.sh` | One-time host prep (directories, permissions, GPU check) | DGX Spark |
| `ingest.py` | CLI helper to bulk-upload a local folder to Open WebUI for RAG | Dev laptop |
| `openwebui_mcp.py` | MCP server exposing Open WebUI RAG as Claude Code tools | Dev laptop |
| `.claude/commands/rag.md` | `/rag` slash command for RAG queries inside Claude Code | Dev laptop |
| `.mcp.json.example` | Template for the project-scoped MCP config (committed) | Dev laptop |
| `.mcp.json` | Your local MCP config (not committed — copy from example) | Dev laptop |
| `deploy.sh` | Rsync this project from the laptop to the Spark over SSH | Dev laptop |
| `health-check.sh` | Verify Ollama and Open WebUI containers are up and responding | DGX Spark |

---

# Part 1 — Server Setup (DGX Spark)

## Models pre-downloaded on first boot

| Model | Type | Why it's here |
|---|---|---|
| `gemma3:27b` | Multimodal (vision + text) | Image understanding, visual QA, large context |
| `llama3.2-vision` | Multimodal (vision + text) | Strong multimodal reasoning, large context |
| `nomic-embed-text` | Embeddings | Powers RAG document search in Open WebUI |

You can add or swap models by editing the `ollama-pull` service's `command` block in `docker-compose.yml`.
Browse available models at [ollama.com/library](https://ollama.com/library).

---

## Prerequisites

- NVIDIA DGX Spark with NVIDIA drivers installed
- [Docker Engine](https://docs.docker.com/engine/install/) ≥ 24.x
- [Docker Compose plugin](https://docs.docker.com/compose/install/) ≥ 2.x
- [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html) configured

Verify the NVIDIA runtime is registered with Docker:

```bash
docker info | grep -i runtime
# Should show: Runtimes: nvidia runc
```

---

## Quick start

### 1. Clone / copy these files into a working directory

```bash
mkdir ~/ollama-stack && cd ~/ollama-stack
# place docker-compose.yml, .env.example, setup.sh here
```

### 2. Create your `.env` file

```bash
cp .env.example .env
# Edit .env and set a strong WEBUI_SECRET_KEY
# Optionally adjust data paths and port numbers
```

### 3. Run the one-time setup script

```bash
chmod +x setup.sh
./setup.sh
```

This creates the bind-mount directories on your NVMe storage and verifies GPU visibility.

### 4. Start the stack

```bash
docker compose up -d
```

Docker will:
1. Pull the Ollama and Open WebUI images
2. Start the Ollama backend
3. Run the `ollama-pull` service to download all three models (this takes a few minutes depending on model sizes)
4. Start Open WebUI once Ollama is healthy

### 5. Open the UI

```
http://<spark-hostname>:3000
```

Create your admin account on first visit.

---

## Storage layout

Model weights and application data are stored in bind-mounted directories on the host so they survive container upgrades:

```
/data/ollama/        ← Ollama model blobs and manifests
/data/open-webui/    ← WebUI database, uploaded docs, user config
```

These paths are configurable via `OLLAMA_DATA_PATH` and `WEBUI_DATA_PATH` in `.env`.
On a DGX Spark, point these at your fast NVMe mount (e.g. `/data`, `/mnt/nvme`) for best performance.

---

## Adding more models

Edit the `ollama-pull` service command in `docker-compose.yml`:

```yaml
command:
  - |
    ollama pull gemma3:27b
    ollama pull llama3.2-vision
    ollama pull nomic-embed-text
    ollama pull qwen2.5:72b        # ← add new models here
```

Then run:

```bash
docker compose up ollama-pull
```

You can also pull models on demand from inside the Ollama container:

```bash
docker exec -it ollama ollama pull <model-name>
```

---

## Performance tuning

The following environment variables in `docker-compose.yml` (and `.env`) control Ollama's behavior:

| Variable | Default | Description |
|---|---|---|
| `OLLAMA_MAX_LOADED_MODELS` | 3 | Max models resident in VRAM simultaneously |
| `OLLAMA_NUM_PARALLEL` | 2 | Concurrent inference requests per model |
| `OLLAMA_FLASH_ATTENTION` | 1 | Flash attention (faster, less memory) |

The DGX Spark's large unified memory pool means you can increase `OLLAMA_MAX_LOADED_MODELS` and load larger quantizations (e.g. `q8_0` or even `f16`) compared to typical GPU setups.

---

## Health check

`health-check.sh` verifies both containers are running and responding to HTTP. Run it on the Spark after starting the stack:

```bash
chmod +x health-check.sh   # once
./health-check.sh
# PASS: Ollama container healthy
# PASS: Open WebUI container healthy
```

Exits `0` if both pass, `1` if either fails. Useful in scripts or after a reboot.

---

## Useful server commands

```bash
# Start everything
docker compose up -d

# Follow logs for all services
docker compose logs -f

# Follow only model download progress
docker compose logs -f ollama-pull

# Check which models are loaded
docker exec -it ollama ollama list

# Stop the stack (data is preserved)
docker compose down

# Full teardown including volumes (DELETES model weights)
docker compose down -v
```

---

## Security notes

- **Change `WEBUI_SECRET_KEY`** before exposing the stack to any network — this key signs user sessions.
- The WebUI port (3000) is bound to all interfaces by default. If the DGX Spark is network-accessible, consider binding to `127.0.0.1:3000` and using a reverse proxy (nginx/caddy) with TLS.
- The Ollama API port (11434) is also exposed to the host. Firewall it if you don't need external API access.

---

# Part 2 — Dev Laptop Setup

## Prerequisites

- **Node.js / npx** — required for `ollama-mcp` (`npx -y ollama-mcp`); any recent Node LTS works. Verify with `node --version`. Install via [nodejs.org](https://nodejs.org) or `brew install node` on macOS.
- **conda** — required for `openwebui_mcp.py` (the RAG MCP server). Install via [docs.conda.io](https://docs.conda.io) or `brew install miniconda` on macOS.
- **Claude Code** — for MCP-based Ollama and RAG access from the terminal

## Environment variables

Set these in your shell profile (`.zshrc`, `.bashrc`, etc.) or in `.env`:

```bash
export SPARK_OLLAMA_HOST=http://<your-spark-hostname>:11434   # used by ollama-mcp
export OPENWEBUI_API_KEY=sk-...                               # Open WebUI → Settings → Account → API Keys
export OPENWEBUI_URL=http://<your-spark-hostname>:3000        # used by openwebui_mcp.py and ingest.py
```

`OPENWEBUI_API_KEY` and `OPENWEBUI_URL` can also be set in `.env` — `openwebui_mcp.py` loads it automatically.

> **Getting an API key from Open WebUI:** API key creation is not enabled by default. You must first create a **Group** (Admin Panel → Groups) that has API key permissions enabled, then add your user to that group — even if your account is already an Admin. Once the group is configured, navigate to **Settings → Account → API Keys**, click "Show", and create a new key. You'll need to manually copy the key from the UI. See [this discussion](https://github.com/open-webui/open-webui/discussions/19854) for more details. Full admin docs are at [docs.openwebui.com](https://docs.openwebui.com).

## Deploy to Spark — `deploy.sh`

`deploy.sh` rsyncs every git-tracked file (plus `.env`) from your laptop to the Spark over SSH. Run it whenever you change `docker-compose.yml`, `.env`, or any other project file.

**Prerequisites:** `rsync` installed on the laptop, SSH access to the Spark (key-based auth recommended).

**Configure** the three deploy variables in your `.env` (they are never committed):

```
SPARK_SSH_USER=your_username
SPARK_SSH_HOST=your-spark-hostname
SPARK_DEPLOY_DIR=/home/your_username/ollama-stack
```

**Run:**

```bash
chmod +x deploy.sh   # once
./deploy.sh
```

The script uses `git ls-files` to determine what to copy, so new files must be staged (`git add`) before they'll be included. `.env` is always included regardless of git status.

---

## MCP configuration

`.mcp.json` (gitignored) at the repo root configures Claude Code to connect to Ollama as an MCP server.

**Prerequisite:** Node.js must be installed — the MCP server runs via `npx`.

```bash
node --version   # must print a version (e.g. v22.x.x)
npx --version    # must print a version
```

If either command fails, install Node.js first: `brew install node` on macOS, or download from [nodejs.org](https://nodejs.org).

Copy the example config to get started:

```bash
cp .mcp.json.example .mcp.json
```

The file registers two MCP servers:

```json
{
  "mcpServers": {
    "ollama": {
      "type": "stdio",
      "command": "npx",
      "args": ["-y", "ollama-mcp"],
      "env": {
        "OLLAMA_HOST": "${SPARK_OLLAMA_HOST:-http://your-spark-hostname:11434}"
      }
    },
    "openwebui": {
      "type": "stdio",
      "command": "/opt/homebrew/Caskroom/miniconda/base/envs/openwebui-mcp/bin/python",
      "args": ["openwebui_mcp.py"],
      "env": {
        "OPENWEBUI_URL": "${OPENWEBUI_URL:-http://your-spark-hostname:3000}",
        "OPENWEBUI_API_KEY": "${OPENWEBUI_API_KEY}",
        "OPENWEBUI_DEFAULT_MODEL": "gemma3:27b"
      }
    }
  }
}
```

Adjust the conda python path if your miniconda is installed elsewhere (`which python` inside the activated env).

**One-time conda setup for `openwebui_mcp.py`:**

```bash
conda create -n openwebui-mcp python=3.11 -y
conda activate openwebui-mcp
pip install mcp requests python-dotenv
```

**Verify both MCP servers are registered:**

```bash
claude mcp list
# Should show: ollama, openwebui
```

**Verify they connect inside a session:**

```
/mcp
# Should show: ollama     Connected
#              openwebui  Connected
```

**To override the Spark hostname for a session:**

```bash
SPARK_OLLAMA_HOST=http://192.168.1.50:11434 claude
```

**Verify MCP end-to-end with a quick test:**

Once inside a Claude Code session with MCP connected, ask Claude to:

1. List models on the Spark — invokes the `list` tool and returns what's loaded
2. Send a test prompt to a model — invokes `chat_completion` and returns a response

Example exchange:
```
You:    "List the Ollama models on the Spark"
Claude: [calls list tool → returns gemma3:27b, llama3.2-vision, etc.]

You:    "Using gemma3:27b, write a one-liner that prints today's date in bash"
Claude: [calls chat_completion → model responds with: date +"%Y-%m-%d"]
```

If both steps work, the full MCP path (laptop → ollama-mcp → Spark → model → response) is confirmed.

## RAG ingestion — `ingest.py`

`ingest.py` runs on the **dev laptop** and talks to Open WebUI over HTTP.
Point it at your Spark with `--url`:

```bash
# Install dependency once
pip install requests

export OPENWEBUI_API_KEY=sk-...

# Upload an entire folder (creates a knowledge base named after the folder)
./ingest.py /path/to/docs --url http://<your-spark-hostname>:3000

# Explicit knowledge-base name
./ingest.py /path/to/docs --collection "my-project" --url http://<your-spark-hostname>:3000

# Preview without uploading
./ingest.py /path/to/docs --dry-run
```

Supported file types: `.pdf .txt .md .rst .csv .docx .xlsx .pptx .html .xml .json`

---

# Part 3 — Usage

## Multimodal via Claude Code + MCP

With the MCP server connected, Claude Code can invoke Ollama directly during a session.

**Available MCP tools** (exposed by `ollama-mcp`):

| Tool | What it does |
|---|---|
| `list` | List models available on the Spark |
| `chat_completion` | Send a prompt (text or multimodal) to a model |
| `run` | Run a model with a single prompt |
| `pull` | Pull a new model from ollama.com/library |
| `show` | Show model metadata / system prompt |
| `copy` | Copy a model under a new name |
| `remove` | Delete a model from the Spark |

**Example workflows in a Claude Code session:**

```
"List the Ollama models on the Spark"
→ invokes list tool

"Using llama3.2-vision, describe what's in this image: [base64 or file path]"
→ invokes chat_completion with vision content

"Pull qwen2.5:72b onto the Spark"
→ invokes pull tool
```

For multimodal prompts over MCP, images must be passed as base64-encoded strings in the message content.

## Multimodal via Open WebUI browser

1. Open `http://<spark-hostname>:3000`
2. Select `gemma3:27b` or `llama3.2-vision` from the model dropdown
3. Click the **paperclip / image attachment** button in the chat input
4. Upload an image alongside your prompt

Example prompts:
- Upload a diagram → *"Explain what this architecture diagram shows"*
- Upload a chart → *"Summarize the trends in this chart"*
- Upload a photo → *"Describe what you see and identify any text"*

## Speech-to-text (Whisper)

> **Not currently enabled.** The Whisper STT integration was removed from the active configuration. It is a candidate for future enhancement.

Open WebUI supports GPU-accelerated speech-to-text via `faster-whisper` running locally inside the container — no external API required. To enable it in a future iteration, the `open-webui` service would need:

- Image: `ghcr.io/open-webui/open-webui:cuda` (includes CUDA libraries)
- `runtime: nvidia` on the service so the GPU is visible inside the container
- The following environment variables:

| Variable | Example value | Notes |
|---|---|---|
| `ENABLE_AUDIO_TRANSCRIPTION` | `True` | Turns on the STT feature |
| `WHISPER_MODEL` | `large-v3` | ~3 GB, downloaded from HuggingFace on first use |
| `WHISPER_COMPUTE_TYPE` | `float16` | GPU mode; use `int8` for CPU-only |
| `DEVICE_TYPE` | `cuda` | Tells Open WebUI to use the GPU |

The model would be cached at `/data/open-webui/cache/whisper/models` and persist across container upgrades.

---

## RAG document chat

Open WebUI has built-in RAG support using `nomic-embed-text` for embeddings.

**Bulk ingestion via CLI** (recommended for large folders) — see [ingest.py section above](#rag-ingestion----ingestpy).

**Manual upload via UI:**

1. Go to **Workspace → Knowledge** and create a knowledge base
2. Upload PDFs, text files, or paste URLs
3. In a chat, click the **+** button and select the knowledge base

To configure the embedding model:
**Settings → Admin → Documents → Embedding Model** → set to `nomic-embed-text`

---

## RAG via Claude Code + MCP

`openwebui_mcp.py` exposes Open WebUI's RAG pipeline as native MCP tools, so Claude Code can query your knowledge collections directly from a session.

**Available tools** (exposed by `openwebui` MCP server):

| Tool | What it does |
|---|---|
| `list_collections` | List knowledge base collections in Open WebUI |
| `rag_query` | Answer a question via vector search + context injection + Ollama |

**Usage in a Claude Code session:**

```
"List my Open WebUI knowledge collections"
→ invokes list_collections

"Using my project-docs collection, what are the deployment steps?"
→ invokes rag_query(question=..., collection_name="project-docs")
```

**`/rag` slash command** — shorthand that routes through the MCP tools automatically:

```
/rag what are the network requirements?
/rag summarize the architecture in collection project-docs
```

If no collection name is given, Claude will call `list_collections` first and ask which to use.
