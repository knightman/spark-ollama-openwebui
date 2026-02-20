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
