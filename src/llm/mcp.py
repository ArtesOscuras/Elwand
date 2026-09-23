import json
import requests


def call(endpoint, tool_name, arguments, timeout=20):
    """Call an MCP tool via JSON-RPC 2.0 over HTTP, parse SSE response.

    Returns the first text content block from the result, or None on failure.
    """
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": tool_name,
            "arguments": arguments,
        },
    }
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "User-Agent": "opencode/Elwand",
    }
    try:
        resp = requests.post(endpoint, json=payload, headers=headers, timeout=timeout)
    except Exception:
        return None

    if resp.status_code != 200:
        return None

    return _parse_sse(resp.text)


def _parse_sse(text):
    for line in text.split("\n"):
        if not line.startswith("data: "):
            continue
        try:
            data = json.loads(line[6:])
        except json.JSONDecodeError:
            continue
        content = data.get("result", {}).get("content", [])
        for item in content:
            if item.get("type") == "text" and item.get("text"):
                return item["text"]
    return None
