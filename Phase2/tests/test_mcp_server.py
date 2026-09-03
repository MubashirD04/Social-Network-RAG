"""
Regression tests for mcp_server/server.py's get_person_network tool, which
previously had two bugs:

1. It assumed GET /graph/{id}/people returned {"people": [...]}, but the
   real endpoint returns a bare JSON array — calling .get() on a list raised
   AttributeError on every invocation.
2. Even with that fixed, it matched the requested person_name against the
   "name" field, which is the internal p_-prefixed graph node id
   (e.g. "p_Alice"), not the human-readable name — so a lookup for "Alice"
   would never match.

These tests monkeypatch httpx.AsyncClient.get so they don't need a running
API server.
"""
import asyncio
from unittest.mock import patch

from mcp_server import server as mcp_server_module


class _FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload
        self.text = str(payload)

    def json(self):
        return self._payload


def _people_payload():
    return [
        {"name": "p_Alice", "label": "Alice", "pagerank": 0.5, "community": 0},
        {"name": "p_Bob", "label": "Bob", "pagerank": 0.2, "community": 0},
    ]


def test_get_person_network_handles_bare_list_response():
    async def fake_get(self, url, *args, **kwargs):
        return _FakeResponse(200, _people_payload())

    with patch("httpx.AsyncClient.get", new=fake_get):
        result = asyncio.run(mcp_server_module.get_person_network("some-id", "Alice"))

    assert result["name"] == "p_Alice"
    assert result["label"] == "Alice"


def test_get_person_network_matches_case_insensitively_on_label():
    async def fake_get(self, url, *args, **kwargs):
        return _FakeResponse(200, _people_payload())

    with patch("httpx.AsyncClient.get", new=fake_get):
        result = asyncio.run(mcp_server_module.get_person_network("some-id", "bob"))

    assert result["label"] == "Bob"


def test_get_person_network_reports_missing_person():
    async def fake_get(self, url, *args, **kwargs):
        return _FakeResponse(200, _people_payload())

    with patch("httpx.AsyncClient.get", new=fake_get):
        result = asyncio.run(mcp_server_module.get_person_network("some-id", "Nonexistent"))

    assert "error" in result
