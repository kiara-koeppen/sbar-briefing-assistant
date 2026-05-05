"""Agentic SBAR draft generator.

Calls a Foundation Model (Claude Sonnet on Databricks) with one tool:
`search_corpus`, which routes to the existing Knowledge Assistant. The LLM
decides when to look something up vs. when it has enough to draft, then
returns the final SBAR markdown.

When the author has been editing a previous draft and asks to regenerate,
that edited markdown is passed in as context so the model preserves their
changes where they don't conflict with new evidence.
"""
import os
import json
import logging
from datetime import date
import httpx
from databricks.sdk.core import Config

from .ka import ask as ka_ask

log = logging.getLogger(__name__)

LLM_MODEL = os.getenv("LLM_MODEL_NAME", "databricks-claude-sonnet-4-6")
MAX_TURNS = 6
TURN_TIMEOUT = 90.0


SYSTEM_PROMPT = """You are a healthcare executive briefing writer for a regional health system.

Your job is to produce SBAR briefings (Situation, Background, Assessment, Recommendation) for the C-suite. Each briefing must be:
- Grounded in specific data and evidence (cite figures from source materials)
- Concise. Executives have limited time
- Action-oriented (recommendations should have owners and target dates)

You have a tool `search_corpus` that searches the organization's existing knowledge base (KPI exports, prior SBARs, board memos, contracts, policy docs). Use it to:
- Verify or enrich claims in the source materials with established context
- Find historical precedent ("have we tried this before?", "what did the prior pilot show?")
- Pull operational figures, thresholds, or names of programs the author may not have included

Your final output MUST be a complete SBAR markdown document with this exact structure:

# [Title from author's instruction]

**Author:** [author name from context]
**Date:** [today's date]
**Audience:** [from instruction]

## Situation
[2-3 sentences: what is happening, with key figures]

## Background
[Bullets or short paragraphs: what led to this situation; reference precedent or prior context where it strengthens the brief]

## Assessment
[Analysis of root cause and risks if no action; cite cohort/financial data]

## Recommendation
[Numbered list: specific actions with owners and target dates]

When the author provides a "current draft" they have been editing, preserve their wording and structure where it does not conflict with new evidence. Only change what new information requires.

Cite specific numbers from the source materials and corpus. Do not invent data. If you do not have a number you would like to cite, search the corpus or omit the claim.

CRITICAL: Your final response must be ONLY the SBAR markdown document, starting with `# [Title]`. Do not include any preamble, commentary, summary of what you found, or "here is the SBAR" framing. The author will see your raw output as their draft."""


def _endpoint_url() -> str:
    cfg = Config()
    base = cfg.host.rstrip("/")
    if not base.startswith("http"):
        base = f"https://{base}"
    return f"{base}/serving-endpoints/{LLM_MODEL}/invocations"


def _auth_headers() -> dict:
    cfg = Config()
    h = cfg.authenticate()
    h["Content-Type"] = "application/json"
    return h


SEARCH_TOOL = {
    "type": "function",
    "function": {
        "name": "search_corpus",
        "description": "Search the supplemental documents corpus (KPI exports, prior SBARs, board memos, contracts, policy docs) for additional context, facts, figures, or historical precedent. Returns a synthesized answer with citations.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "A focused question to search the corpus with",
                }
            },
            "required": ["query"],
        },
    },
}


def generate_draft(
    *,
    author_email: str,
    instruction: str,
    title: str,
    audience: str,
    source_docs: list[dict],
    current_draft: str | None = None,
) -> dict:
    """Run the agentic loop. Returns:
        {
          "markdown": str,
          "corpus_searches": [{"query": str, "answer": str, "sources": [str]}, ...],
          "turns_used": int,
        }
    """
    sources_block = "\n\n---\n\n".join(
        f"### Source: {d['filename']}\n\n{d['content']}" for d in source_docs
    ) or "(no source documents uploaded)"

    user_msg = (
        f"Title: {title}\n"
        f"Audience: {audience}\n"
        f"Author: {author_email}\n"
        f"Today: {date.today().isoformat()}\n\n"
        f"Author's instruction:\n{instruction}\n\n"
        f"Newly uploaded source materials for this draft:\n{sources_block}\n"
    )
    if current_draft:
        user_msg += (
            "\n\n---\n\nCurrent draft (the author has been editing this version - "
            "preserve their edits where possible, only revise what new evidence "
            "requires):\n\n" + current_draft
        )

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_msg},
    ]
    corpus_searches: list[dict] = []
    url = _endpoint_url()
    headers = _auth_headers()

    for turn in range(MAX_TURNS):
        body = {
            "messages": messages,
            "max_tokens": 4000,
            "tools": [SEARCH_TOOL],
        }
        with httpx.Client(timeout=TURN_TIMEOUT) as client:
            r = client.post(url, headers=headers, json=body)
            r.raise_for_status()
            resp = r.json()

        choice = resp["choices"][0]
        msg = choice["message"]
        finish = choice.get("finish_reason")
        tool_calls = msg.get("tool_calls") or []

        if not tool_calls:
            text = (msg.get("content") or "").strip()
            # Strip any preamble before the first H1 heading. Even with explicit
            # prompting the model occasionally narrates ("I now have enough
            # context...") before the SBAR. We want the published markdown to
            # start with the title.
            idx = text.find("\n# ")
            if idx == -1 and text.startswith("# "):
                clean = text
            elif idx != -1:
                clean = text[idx + 1:]
            else:
                clean = text
            return {
                "markdown": clean.strip(),
                "corpus_searches": corpus_searches,
                "turns_used": turn + 1,
            }

        # Append assistant message verbatim so the conversation is consistent.
        messages.append({
            "role": "assistant",
            "content": msg.get("content") or "",
            "tool_calls": tool_calls,
        })

        for tc in tool_calls:
            fn = tc.get("function", {})
            name = fn.get("name")
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {}

            if name == "search_corpus":
                query = args.get("query", "")
                log.info("agent search_corpus: %s", query)
                ka_result = ka_ask(query, timeout=45.0)
                citations = [s.get("filename", "") for s in ka_result.get("sources", [])]
                corpus_searches.append({
                    "query": query,
                    "answer": ka_result.get("answer", ""),
                    "sources": citations,
                })
                tool_content = ka_result.get("answer", "")
                if citations:
                    tool_content += "\n\nCitations: " + ", ".join(citations)
            else:
                tool_content = f"Unknown tool: {name}"

            messages.append({
                "role": "tool",
                "tool_call_id": tc.get("id"),
                "content": tool_content,
            })

    raise RuntimeError(f"LLM agent exceeded {MAX_TURNS} turns without producing a final draft")
