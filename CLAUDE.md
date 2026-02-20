# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

A Docker Compose stack that runs Ollama (LLM inference backend) + Open WebUI (browser frontend) with GPU acceleration on an NVIDIA DGX Spark. No application code — just infrastructure configuration files.

## Key commands

```bash
# First-time setup (creates host directories, verifies NVIDIA runtime)
cp .env.example .env   # then edit WEBUI_SECRET_KEY
./setup.sh

# Start the full stack (detached)
docker compose up -d

# Pull/refresh models only
docker compose up ollama-pull

# Tail logs
docker compose logs -f
docker compose logs -f ollama-pull   # watch model download progress

# Stop (data preserved)
docker compose down

# Inspect loaded models
docker exec -it ollama ollama list

# Pull a model on demand
docker exec -it ollama ollama pull <model-name>
```

## Architecture

Three Docker services on a shared bridge network (`ollama_net`):

- **ollama** — inference backend; exposes API on port 11434; data persisted to bind-mount at `OLLAMA_DATA_PATH` (default `/data/ollama`)
- **ollama-pull** — one-shot init container that pulls models after `ollama` is healthy, then exits (`restart: "no"`)
- **open-webui** — browser UI on port 3000 (maps to internal 8080); depends on `ollama` being healthy; data at `WEBUI_DATA_PATH` (default `/data/open-webui`)

Both data volumes use `driver: local` with `o: bind` — they are bind mounts to host paths, not Docker-managed volumes, so model weights survive `docker compose down -v`.

## Configuration

All tunables live in `.env` (copy from `.env.example`). The `docker-compose.yml` hardcodes fallback values; `.env` overrides take precedence via `docker compose`'s automatic env file loading.

Key variables:
- `WEBUI_SECRET_KEY` — must be changed before network exposure
- `OLLAMA_MAX_LOADED_MODELS` / `OLLAMA_NUM_PARALLEL` / `OLLAMA_FLASH_ATTENTION` — VRAM/throughput tuning
- `OLLAMA_DATA_PATH` / `WEBUI_DATA_PATH` — point to fast NVMe on DGX Spark

## RAG ingestion helper (`ingest.py`)

`ingest.py` bulk-uploads a local folder to Open WebUI's knowledge base API for RAG. It requires only `requests` (`pip install requests`) and an API key generated from Open WebUI → Settings → Account → API Keys (set as `OPENWEBUI_API_KEY`).

The script uploads each file, polls `GET /api/v1/files/{id}/process/status` until processing completes, then calls `POST /api/v1/knowledge/{id}/file/add`. It creates the knowledge base if it doesn't exist.

```bash
./ingest.py /path/to/docs                        # collection name = folder name
./ingest.py /path/to/docs --collection "name"    # explicit collection
./ingest.py /path/to/docs --dry-run              # preview only
```

## Adding or swapping models

Edit the `ollama-pull` service `command` block in `docker-compose.yml`, then run `docker compose up ollama-pull`. Browse available models at [ollama.com/library](https://ollama.com/library).

## Security

- `WEBUI_SECRET_KEY` signs user sessions — rotate before any network exposure.
- Port 3000 (WebUI) and 11434 (Ollama API) bind to all interfaces by default. Restrict to `127.0.0.1` and front with a TLS reverse proxy (nginx/caddy) for network-accessible deployments.

## RAG ingestion helper (`ingest.py`)

`ingest.py` runs on the **dev laptop** and talks to Open WebUI over HTTP. It requires only `requests` (`pip install requests`) and an API key from Open WebUI → Settings → Account → API Keys (set as `OPENWEBUI_API_KEY`). Pass `--url http://spark1:3000` (or whatever hostname/IP the Spark is reachable at).

The script uploads each file, polls `GET /api/v1/files/{id}/process/status` until processing completes, then calls `POST /api/v1/knowledge/{id}/file/add`. It creates the knowledge base if it doesn't exist.

```bash
./ingest.py /path/to/docs --url http://spark1:3000                        # collection name = folder name
./ingest.py /path/to/docs --url http://spark1:3000 --collection "name"    # explicit collection
./ingest.py /path/to/docs --dry-run                                       # preview only
```

## Which machine runs what

| File / component | DGX Spark | Dev laptop |
|---|---|---|
| `docker-compose.yml` | ✓ | |
| `.env.example` / `.env` | ✓ | |
| `setup.sh` | ✓ | |
| Ollama container (port 11434) | ✓ | |
| Open WebUI container (port 3000) | ✓ | |
| `ingest.py` | | ✓ |
| `health-check.sh` | ✓ | |
| `.mcp.json.example` / `.mcp.json` (Claude Code MCP config) | | ✓ |
| `claude` CLI / Claude Code session | | ✓ |

## MCP configuration

`.mcp.json` (gitignored) at the repo root tells Claude Code to launch `ollama-mcp` (via `npx -y ollama-mcp`) as a stdio MCP server. The server reads `OLLAMA_HOST` to find the Spark. Copy `.mcp.json.example` to `.mcp.json` and adjust the hostname.

```bash
cp .mcp.json.example .mcp.json   # then set SPARK_OLLAMA_HOST or edit the hostname
```

**Shell env var:** set `SPARK_OLLAMA_HOST` in your shell profile; `.mcp.json` passes it through as `OLLAMA_HOST`. If unset, the default `http://spark1:11434` is used.

```bash
export SPARK_OLLAMA_HOST=http://spark1:11434   # or IP address
```

**Verify registration (outside a session):**

```bash
claude mcp list        # should list: ollama
```

**Verify connection (inside a session):**

```
/mcp               # should show: ollama  Connected
```

**Override hostname for one session:**

```bash
SPARK_OLLAMA_HOST=http://192.168.1.50:11434 claude
```

**MCP tools exposed by `ollama-mcp`:**

| Tool | What it does |
|---|---|
| `list` | List models available on the Spark |
| `chat_completion` | Send a prompt (text or multimodal) to a model |
| `run` | Run a model with a single prompt |
| `pull` | Pull a new model from ollama.com/library |
| `show` | Show model metadata / system prompt |
| `copy` | Copy a model under a new name |
| `remove` | Delete a model from the Spark |

**Verify MCP end-to-end (inside a session):**

Ask Claude to run two back-to-back checks — this exercises the full path from laptop through `ollama-mcp` to the Spark:

```
"List the Ollama models on the Spark"              → invokes list tool
"Using gemma3:27b, write a hello-world bash line"  → invokes chat_completion
```

Both should return results. If `list` works but `chat_completion` hangs, the model may still be loading.

**Troubleshooting checklist:**
- `node` / `npx` installed on the laptop? (`node --version`)
- Spark reachable from laptop? (`curl http://spark1:11434/api/tags`)
- Ollama container running on Spark? (`docker compose ps` on the Spark)
- `SPARK_OLLAMA_HOST` set correctly in the shell that launched `claude`?

## Multimodal usage

Models that support vision: `llama3.2-vision`, `gemma3:27b`.

**Path 1 — MCP (Claude Code session):**
Ask Claude to use a specific model with image content. Images must be passed as base64-encoded strings in the message content when going through the MCP `chat_completion` tool.

```
"Using llama3.2-vision, describe what's in this image: <base64 string>"
"List models on the Spark"                          → invokes list
"Pull qwen2.5:72b onto the Spark"                   → invokes pull
```

**Path 2 — Browser (Open WebUI):**
Open `http://<spark-hostname>:3000`, select a vision model from the dropdown, and use the paperclip / image attachment button to upload an image alongside your prompt.
