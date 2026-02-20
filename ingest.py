#!/usr/bin/env python3
"""
ingest.py – Bulk-upload a local folder to Open WebUI for RAG ingestion.

Usage:
    ./ingest.py <folder> [options]

Options:
    --url URL           Base URL of Open WebUI (default: http://localhost:3000)
    --collection NAME   Knowledge-base name to create or append to (default: folder name)
    --api-key KEY       API key (or set OPENWEBUI_API_KEY env var)
    --ext a,b,c         Comma-separated extra file extensions to include
    --dry-run           List files that would be uploaded without uploading

Auth:
    Generate your API key in Open WebUI → Settings → Account → API Keys.
    Export it as:  export OPENWEBUI_API_KEY=sk-...
"""

import argparse
import mimetypes
import os
import sys
import time
from pathlib import Path

try:
    import requests
except ImportError:
    sys.exit("requests is required: pip install requests")

# File types Open WebUI can extract text from
DEFAULT_EXTENSIONS = {
    ".pdf", ".txt", ".md", ".rst", ".csv",
    ".docx", ".doc", ".xlsx", ".xls", ".pptx",
    ".html", ".htm", ".xml", ".json",
}

POLL_INTERVAL = 2   # seconds between status checks
POLL_TIMEOUT  = 120 # seconds before giving up on a single file


def build_session(api_key: str) -> requests.Session:
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {api_key}"})
    return s


def get_or_create_knowledge(session: requests.Session, base_url: str, name: str) -> str:
    """Return the ID of an existing knowledge base by name, or create one."""
    r = session.get(f"{base_url}/api/v1/knowledge/", timeout=10)
    r.raise_for_status()
    for kb in r.json():
        if kb.get("name") == name:
            print(f"[kb] Using existing knowledge base '{name}' ({kb['id']})")
            return kb["id"]

    r = session.post(
        f"{base_url}/api/v1/knowledge/create",
        json={"name": name, "description": f"Ingested from local folder: {name}"},
        timeout=10,
    )
    r.raise_for_status()
    kb_id = r.json()["id"]
    print(f"[kb] Created knowledge base '{name}' ({kb_id})")
    return kb_id


def upload_file(session: requests.Session, base_url: str, path: Path) -> str:
    """Upload a file and return its ID."""
    mime = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
    with open(path, "rb") as fh:
        r = session.post(
            f"{base_url}/api/v1/files/",
            files={"file": (path.name, fh, mime)},
            timeout=60,
        )
    r.raise_for_status()
    file_id = r.json()["id"]
    return file_id


def wait_for_processing(session: requests.Session, base_url: str, file_id: str) -> bool:
    """Poll until the file is processed. Returns True on success."""
    deadline = time.time() + POLL_TIMEOUT
    while time.time() < deadline:
        r = session.get(f"{base_url}/api/v1/files/{file_id}/process/status", timeout=10)
        if r.status_code == 404:
            # Endpoint may not exist on older builds — assume ready
            return True
        r.raise_for_status()
        status = r.json().get("status", "")
        if status == "completed":
            return True
        if status == "failed":
            return False
        time.sleep(POLL_INTERVAL)
    return False


def add_to_knowledge(session: requests.Session, base_url: str, kb_id: str, file_id: str) -> None:
    r = session.post(
        f"{base_url}/api/v1/knowledge/{kb_id}/file/add",
        json={"file_id": file_id},
        timeout=30,
    )
    r.raise_for_status()


def collect_files(folder: Path, extensions: set[str]) -> list[Path]:
    return sorted(
        p for p in folder.rglob("*")
        if p.is_file() and p.suffix.lower() in extensions
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("folder",      help="Folder to ingest")
    parser.add_argument("--url",       default="http://localhost:3000", help="Open WebUI base URL")
    parser.add_argument("--collection", dest="collection", help="Knowledge-base name (default: folder name)")
    parser.add_argument("--api-key",   dest="api_key", help="API key (overrides OPENWEBUI_API_KEY)")
    parser.add_argument("--ext",       help="Extra extensions to include, e.g. .log,.yaml")
    parser.add_argument("--dry-run",   action="store_true", help="List files without uploading")
    args = parser.parse_args()

    # ── Resolve inputs ────────────────────────────────────────────────────────
    folder = Path(args.folder).expanduser().resolve()
    if not folder.is_dir():
        sys.exit(f"Not a directory: {folder}")

    api_key = args.api_key or os.environ.get("OPENWEBUI_API_KEY", "")
    if not api_key and not args.dry_run:
        sys.exit("API key required. Set OPENWEBUI_API_KEY or pass --api-key.")

    collection_name = args.collection or folder.name

    extensions = set(DEFAULT_EXTENSIONS)
    if args.ext:
        extensions |= {e if e.startswith(".") else f".{e}" for e in args.ext.split(",")}

    # ── Collect files ─────────────────────────────────────────────────────────
    files = collect_files(folder, extensions)
    if not files:
        sys.exit(f"No supported files found in {folder}")

    print(f"Found {len(files)} file(s) to ingest into '{collection_name}':")
    for f in files:
        print(f"  {f.relative_to(folder)}")

    if args.dry_run:
        return

    print()
    session = build_session(api_key)
    base_url = args.url.rstrip("/")

    # ── Ensure knowledge base exists ──────────────────────────────────────────
    kb_id = get_or_create_knowledge(session, base_url, collection_name)

    # ── Upload each file ──────────────────────────────────────────────────────
    succeeded, failed = 0, 0
    for i, path in enumerate(files, 1):
        label = path.relative_to(folder)
        print(f"\n[{i}/{len(files)}] {label}")

        try:
            file_id = upload_file(session, base_url, path)
            print(f"  uploaded  → {file_id}")

            print(f"  processing...", end="", flush=True)
            ok = wait_for_processing(session, base_url, file_id)
            print(" done" if ok else " timed-out (proceeding anyway)")

            add_to_knowledge(session, base_url, kb_id, file_id)
            print(f"  added to knowledge base ✓")
            succeeded += 1

        except requests.HTTPError as e:
            body = e.response.text[:200] if e.response is not None else ""
            print(f"  ERROR {e.response.status_code if e.response is not None else ''}: {body}")
            failed += 1
        except Exception as e:  # noqa: BLE001
            print(f"  ERROR: {e}")
            failed += 1

    # ── Summary ───────────────────────────────────────────────────────────────
    print(f"\n── Summary ──────────────────────────────")
    print(f"  Succeeded : {succeeded}")
    print(f"  Failed    : {failed}")
    print(f"  Collection: '{collection_name}' ({kb_id})")
    print(f"  View at   : {base_url}")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
