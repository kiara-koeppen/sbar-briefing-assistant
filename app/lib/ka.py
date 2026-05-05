"""Knowledge Assistant client.

Calls the KA serving endpoint via the Databricks Responses API. Returns the
answer text plus a list of source citations parsed from URL annotations.
"""
import os
import re
import urllib.parse
import httpx
from databricks.sdk.core import Config


def _decode_filename(url: str) -> str:
    """Pull a friendly filename out of the KA's url_citation annotation URL."""
    if not url:
        return ""
    parsed = urllib.parse.urlparse(url)
    path = urllib.parse.unquote(parsed.path)
    return path.rsplit("/", 1)[-1]


def ask(question: str, history: list[dict] | None = None, *, timeout: float = 50.0) -> dict:
    """Send a question to the KA endpoint. Returns:
        {
          "answer": str,
          "sources": [{"filename": str, "url": str}, ...],
          "low_confidence": bool,
        }
    The Databricks Apps proxy times out around 60 s, so cap timeout below that
    and return a graceful error if it expires.
    """
    cfg = Config()
    endpoint = os.getenv("KA_ENDPOINT_NAME", "ka-3306ffae-endpoint")
    url = f"https://{cfg.host}/serving-endpoints/{endpoint}/invocations"
    headers = cfg.authenticate()
    headers["Content-Type"] = "application/json"

    history = history or []
    inputs = list(history) + [{"role": "user", "content": question}]

    body = {"input": inputs, "max_output_tokens": 800}
    try:
        with httpx.Client(timeout=timeout) as client:
            r = client.post(url, headers=headers, json=body)
            r.raise_for_status()
            data = r.json()
    except httpx.TimeoutException:
        return {
            "answer": "The Knowledge Assistant timed out. Please try again.",
            "sources": [], "low_confidence": True, "error": "timeout",
        }

    return _parse_response(data)


def _parse_response(data: dict) -> dict:
    answer_chunks: list[str] = []
    sources: dict[str, dict] = {}
    low_confidence_signals = []

    for item in data.get("output", []):
        if item.get("type") != "message":
            continue
        for c in item.get("content", []):
            if c.get("type") == "output_text":
                answer_chunks.append(c.get("text", ""))
                for ann in c.get("annotations", []) or []:
                    if ann.get("type") == "url_citation":
                        url = ann.get("url", "")
                        title = ann.get("title") or _decode_filename(url)
                        if title not in sources:
                            sources[title] = {"filename": title, "url": url}

    answer = "".join(answer_chunks).strip()
    if not answer:
        answer = "(no answer returned)"

    # Heuristic: if KA explicitly says it doesn't have the data, flag as low-confidence.
    lower = answer.lower()
    low_conf_phrases = [
        "i don't have", "i do not have", "would need to be added",
        "not in the supplemental materials", "cannot be answered",
        "no document", "would be needed",
    ]
    low_confidence = any(p in lower for p in low_conf_phrases)

    return {
        "answer": answer,
        "sources": list(sources.values()),
        "low_confidence": low_confidence,
    }
