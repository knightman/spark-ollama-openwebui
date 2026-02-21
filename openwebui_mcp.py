#!/usr/bin/env python3
"""
openwebui_mcp.py — MCP server that exposes Open WebUI RAG capabilities as tools.

Tools
-----
list_collections    List knowledge base collections in Open WebUI
rag_query           Answer a question via RAG search over a named collection

Configuration (env vars)
------------------------
OPENWEBUI_URL               Base URL, e.g. http://spark_ip_addr:3000
OPENWEBUI_API_KEY           Bearer token — WebUI → Settings → Account → API Keys
OPENWEBUI_DEFAULT_MODEL     Ollama model for inference  (default: gemma3:27b)

Setup
-----
conda create -n openwebui-mcp python=3.11 -y
conda activate openwebui-mcp
pip install mcp requests python-dotenv
"""

import os
from pathlib import Path

import requests
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

# Load .env from the repo root (same directory as this script)
load_dotenv(Path(__file__).parent / ".env")

OPENWEBUI_URL   = os.environ.get("OPENWEBUI_URL", "").rstrip("/")
OPENWEBUI_KEY   = os.environ.get("OPENWEBUI_API_KEY", "")
DEFAULT_MODEL   = os.environ.get("OPENWEBUI_DEFAULT_MODEL", "gemma3:27b")

mcp = FastMCP("openwebui")


def _session() -> requests.Session:
    s = requests.Session()
    if OPENWEBUI_KEY:
        s.headers.update({"Authorization": f"Bearer {OPENWEBUI_KEY}"})
    return s


@mcp.tool()
def list_collections() -> list[dict]:
    """List all knowledge base collections available in Open WebUI."""
    r = _session().get(f"{OPENWEBUI_URL}/api/v1/knowledge/", timeout=10)
    r.raise_for_status()
    data = r.json()
    items = data.get("items", data) if isinstance(data, dict) else data
    return [{"id": kb["id"], "name": kb["name"]} for kb in items]


@mcp.tool()
def rag_query(
    question: str,
    collection_name: str,
    model: str = DEFAULT_MODEL,
) -> str:
    """Answer a question using RAG over an Open WebUI knowledge collection.

    Retrieves relevant chunks from the named collection, injects them as
    context, and forwards the augmented prompt to the specified Ollama model.

    Args:
        question:        The question to answer.
        collection_name: Name of the knowledge collection to search.
        model:           Ollama model to use for inference.
    """
    sess = _session()

    # Resolve collection name → ID
    r = sess.get(f"{OPENWEBUI_URL}/api/v1/knowledge/", timeout=10)
    r.raise_for_status()
    data = r.json()
    collections = data.get("items", data) if isinstance(data, dict) else data

    collection_id = next(
        (kb["id"] for kb in collections if kb["name"] == collection_name), None
    )
    if collection_id is None:
        available = [kb["name"] for kb in collections]
        return f"Collection '{collection_name}' not found. Available: {available}"

    # RAG-augmented chat completion
    r = sess.post(
        f"{OPENWEBUI_URL}/api/chat/completions",
        json={
            "model": model,
            "messages": [{"role": "user", "content": question}],
            "files": [{"type": "collection", "id": collection_id}],
        },
        timeout=120,
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


if __name__ == "__main__":
    mcp.run()
