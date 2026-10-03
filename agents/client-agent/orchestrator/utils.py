from __future__ import annotations

import json
from typing import Any, Dict, List


def extract_result_text(result_data: Any) -> str:
    """Extract human-readable text from common agent response formats."""
    if isinstance(result_data, dict):
        for key in ("answer", "response", "report", "message", "result", "raw_response"):
            value = result_data.get(key)
            if isinstance(value, str) and value.strip():
                return value
            if value and not isinstance(value, (dict, list)):
                return str(value)
        return json.dumps(result_data, indent=2)
    return str(result_data)

def normalize_suggested_queries(raw: Any, limit: int = 3) -> List[Dict[str, str]]:
    """Normalize suggested query payloads into UI-friendly metadata entries."""
    if not isinstance(raw, list):
        return []

    results: List[Dict[str, str]] = []
    seen = set()
    for item in raw:
        if isinstance(item, dict):
            query = str(item.get("suggested_query") or item.get("query") or "").strip()
        else:
            query = str(item or "").strip()
        if not query:
            continue
        key = query.lower()
        if key in seen:
            continue
        seen.add(key)
        results.append({"suggested_query": query})
        if len(results) >= limit:
            break
    return results

def collect_suggested_queries(tool_results: Dict[str, Any], limit: int = 3) -> List[Dict[str, str]]:
    """Collect deduplicated suggested queries from skill result payloads."""
    merged: List[Dict[str, str]] = []
    seen = set()
    for result_data in tool_results.values():
        if not isinstance(result_data, dict):
            continue
        for suggestion in normalize_suggested_queries(result_data.get("suggested_queries"), limit=limit):
            query = suggestion.get("suggested_query", "")
            key = query.lower()
            if not query or key in seen:
                continue
            seen.add(key)
            merged.append({"suggested_query": query})
            if len(merged) >= limit:
                return merged
    return merged
