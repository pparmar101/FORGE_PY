from __future__ import annotations

import json
import os
from typing import Generator

import httpx

API_BASE = os.getenv("FORGE_API_URL", "http://127.0.0.1:8000")


def start_run(ticket_id: str) -> dict:
    """POST /runs — returns {run_id, status}."""
    response = httpx.post(f"{API_BASE}/runs", json={"ticket_id": ticket_id}, timeout=10)
    response.raise_for_status()
    return response.json()


def get_run(run_id: str) -> dict:
    """GET /runs/{run_id} — returns RunState as dict."""
    response = httpx.get(f"{API_BASE}/runs/{run_id}", timeout=10)
    response.raise_for_status()
    return response.json()


def stream_run(run_id: str) -> Generator[dict, None, None]:
    """
    GET /runs/{run_id}/stream — yields parsed RunEvent dicts as they arrive.
    Stops when stream_end event is received or connection closes.
    """
    with httpx.stream("GET", f"{API_BASE}/runs/{run_id}/stream", timeout=None) as response:
        response.raise_for_status()
        for line in response.iter_lines():
            if line.startswith("data: "):
                raw = line[6:].strip()
                if not raw:
                    continue
                try:
                    event = json.loads(raw)
                except json.JSONDecodeError:
                    continue

                yield event

                if event.get("event_type") == "stream_end":
                    break
