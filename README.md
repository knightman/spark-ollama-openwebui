# Ollama + Open WebUI on NVIDIA DGX Spark

A self-hosted, GPU-accelerated stack for running context-aware multimodal LLMs locally.  
Includes Ollama as the inference backend, Open WebUI as the browser frontend, and automatic model downloading on first start.

---

## What's included

| File | Purpose |
|---|---|
| `docker-compose.yml` | Full service definition (Ollama, model puller, Open WebUI) |
| `.env.example` | Template for your local environment variables |
| `.env` | Your local environment overrides (not committed) |
| `setup.sh` | One-time host prep (directories, permissions, GPU check) |
| `ingest.py` | CLI helper to bulk-upload a local folder to Open WebUI for RAG |

---

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
http://localhost:3000
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

## Using multimodal models

Once the stack is running, select `gemma3:27b` or `llama3.2-vision` from the model dropdown in Open WebUI. Use the paperclip / image attachment button in the chat input to upload an image alongside your prompt.

Example prompts:
- Upload a diagram → *"Explain what this architecture diagram shows"*
- Upload a chart → *"Summarize the trends in this chart"*
- Upload a photo → *"Describe what you see and identify any text"*

---

## Setting up RAG (document-aware chat)

Open WebUI has built-in RAG support that uses `nomic-embed-text` for embeddings.

**Bulk ingestion via CLI** (recommended for large folders):

```bash
# Install dependency once
pip install requests

# Generate an API key: Open WebUI → Settings → Account → API Keys
export OPENWEBUI_API_KEY=sk-...

# Upload an entire folder (creates a knowledge base named after the folder)
./ingest.py /path/to/docs

# Explicit knowledge-base name
./ingest.py /path/to/docs --collection "my-project"

# Preview without uploading
./ingest.py /path/to/docs --dry-run
```

Supported file types: `.pdf .txt .md .rst .csv .docx .xlsx .pptx .html .xml .json`

**Manual upload via UI:**

1. Go to **Workspace → Knowledge** and create a knowledge base
2. Upload PDFs, text files, or paste URLs
3. In a chat, click the **+** button and select the knowledge base

To configure the embedding model:
**Settings → Admin → Documents → Embedding Model** → set to `nomic-embed-text`

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

## Useful commands

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

## Performance tuning

The following environment variables in `docker-compose.yml` (and `.env`) control Ollama's behavior:

| Variable | Default | Description |
|---|---|---|
| `OLLAMA_MAX_LOADED_MODELS` | 3 | Max models resident in VRAM simultaneously |
| `OLLAMA_NUM_PARALLEL` | 2 | Concurrent inference requests per model |
| `OLLAMA_FLASH_ATTENTION` | 1 | Flash attention (faster, less memory) |

The DGX Spark's large unified memory pool means you can increase `OLLAMA_MAX_LOADED_MODELS` and load larger quantizations (e.g. `q8_0` or even `f16`) compared to typical GPU setups.

---

## Security notes

- **Change `WEBUI_SECRET_KEY`** before exposing the stack to any network — this key signs user sessions.
- The WebUI port (3000) is bound to all interfaces by default. If the DGX Spark is network-accessible, consider binding to `127.0.0.1:3000` and using a reverse proxy (nginx/caddy) with TLS.
- The Ollama API port (11434) is also exposed to the host. Firewall it if you don't need external API access.
