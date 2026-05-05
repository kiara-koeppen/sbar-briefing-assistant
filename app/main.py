"""Executive SBAR Briefing Assistant - FastAPI app.

Two surfaces:
  /                     Executive view - render current SBAR + chat with KA
  /author               Author view - engagement dashboard for the SBAR author

All KA interactions and SBAR views are logged to the Lakebase audit_events table.
"""
import os
import io
import re
import uuid
import json
import asyncio
import logging
import pathlib
from datetime import datetime, timezone

import markdown
from fastapi import FastAPI, Request, HTTPException, BackgroundTasks, UploadFile, File, Form
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from databricks.sdk import WorkspaceClient

from lib.auth import current_user, CurrentUser
from lib.db import insert_event, query
from lib.ka import ask as ka_ask
from lib import drafts as drafts_lib
from lib.llm import generate_draft

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

APP_ROOT = pathlib.Path(__file__).parent
SBAR_VOLUME_PATH = os.getenv("SBAR_VOLUME_PATH", "/Volumes/kk_test/sbar_briefing/sbar_documents")
AUTHOR_EMAILS = {e.strip() for e in os.getenv("AUTHOR_USER_EMAILS", "").split(",") if e.strip()}

# Databricks Apps run sandboxed - /Volumes is not auto-mounted on the filesystem.
# Use the SDK's Files API for volume reads/writes.
_workspace_client = WorkspaceClient()

app = FastAPI(title="SBAR Briefing Assistant")
app.mount("/static", StaticFiles(directory=APP_ROOT / "static"), name="static")
templates = Jinja2Templates(directory=APP_ROOT / "templates")


@app.on_event("startup")
def _startup_diag():
    try:
        entries = list(_workspace_client.files.list_directory_contents(SBAR_VOLUME_PATH))
        log.info(f"SBAR volume contains {len(entries)} entries")
    except Exception as e:
        log.exception(f"Volume list failed: {e}")
    log.info(
        f"PG env: PGHOST={os.getenv('PGHOST')!r} PGDATABASE={os.getenv('PGDATABASE')!r} "
        f"PGUSER={os.getenv('PGUSER')!r} PGPASSWORD_set={'PGPASSWORD' in os.environ} "
        f"PGSSLMODE={os.getenv('PGSSLMODE')!r}"
    )


# In-process pending answers keyed by question_id.
# For demo single-replica simplicity. A multi-replica deploy would use Lakebase
# or Redis here; the audit table already captures the full record.
_PENDING: dict[str, dict] = {}


def _user(request: Request) -> CurrentUser:
    return current_user(request, AUTHOR_EMAILS)


def _list_sbars() -> list[dict]:
    """List markdown SBARs in the UC volume via the Files API.
    Title is the first H1 heading found, falling back to the filename."""
    out = []
    try:
        for entry in _workspace_client.files.list_directory_contents(SBAR_VOLUME_PATH):
            if entry.is_directory or not (entry.name or "").endswith(".md"):
                continue
            content = _read_sbar_path(entry.path)
            title = entry.name[:-3]
            for line in (content or "").splitlines():
                if line.startswith("# ") and not line.startswith("## "):
                    title = line[2:].strip()
                    break
            out.append({
                "id": entry.name[:-3],
                "title": title,
                "modified": datetime.fromtimestamp((entry.last_modified or 0) / 1000, tz=timezone.utc).isoformat() if entry.last_modified else "",
            })
    except Exception:
        log.exception("Failed to list SBARs")
    # SBAR file IDs encode the briefing cycle number (e.g. sbar_2025_q4_06_*).
    # Sort by id desc so the most recent cycle is the default.
    out.sort(key=lambda x: x["id"], reverse=True)
    return out


def _read_sbar_path(path: str) -> str:
    resp = _workspace_client.files.download(path)
    return resp.contents.read().decode("utf-8")


def _read_sbar(sbar_id: str) -> str:
    path = f"{SBAR_VOLUME_PATH}/{sbar_id}.md"
    try:
        return _read_sbar_path(path)
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"SBAR not found: {sbar_id} ({e})")


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    user = _user(request)
    sbars = _list_sbars()
    if not sbars:
        return HTMLResponse("<h1>No SBARs published yet.</h1>", status_code=503)
    latest = sbars[0]
    return RedirectResponse(url=f"/sbar/{latest['id']}" + ("?author=1" if user.is_author else ""))


SOURCE_FILENAME_RE = re.compile(r"\b([a-zA-Z][a-zA-Z0-9_-]*\.(md|pdf|txt|docx))\b")


def _linkify_sources_in_md(md_text: str) -> str:
    """Turn references like `pharmacy_callback_pilot_results_2022.md` in the
    SBAR body into clickable markdown links to /api/source/<filename>. Done
    on the markdown source (not the rendered HTML) so it composes cleanly
    with the markdown renderer.
    Skips text inside fenced code blocks and existing markdown links."""
    out = []
    in_code = False
    for raw_line in md_text.splitlines(keepends=True):
        if raw_line.strip().startswith("```"):
            in_code = not in_code
            out.append(raw_line)
            continue
        if in_code:
            out.append(raw_line)
            continue
        # Only linkify filenames that aren't already inside a markdown link.
        # Heuristic: replace by walking through and skipping inside [text](url).
        rebuilt = []
        i = 0
        while i < len(raw_line):
            if raw_line[i] == "[":
                # find matching ](...) and pass through unchanged
                close_bracket = raw_line.find("]", i)
                if close_bracket != -1 and close_bracket + 1 < len(raw_line) and raw_line[close_bracket + 1] == "(":
                    close_paren = raw_line.find(")", close_bracket)
                    if close_paren != -1:
                        rebuilt.append(raw_line[i:close_paren + 1])
                        i = close_paren + 1
                        continue
            m = SOURCE_FILENAME_RE.match(raw_line, i)
            if m:
                fn = m.group(1)
                rebuilt.append(f"[{fn}](/api/source/{fn})")
                i = m.end()
            else:
                rebuilt.append(raw_line[i])
                i += 1
        out.append("".join(rebuilt))
    return "".join(out)


@app.get("/sbar/{sbar_id}", response_class=HTMLResponse)
def view_sbar(request: Request, sbar_id: str):
    user = _user(request)
    md = _read_sbar(sbar_id)
    md = _linkify_sources_in_md(md)
    html = markdown.markdown(md, extensions=["tables", "fenced_code"])
    sbars = _list_sbars()
    title = next((s["title"] for s in sbars if s["id"] == sbar_id), sbar_id)

    session_id = request.cookies.get("sbar_session") or str(uuid.uuid4())
    response = templates.TemplateResponse("exec.html", {
        "request": request,
        "user": user,
        "sbar_id": sbar_id,
        "sbar_title": title,
        "sbar_html": html,
        "all_sbars": sbars,
        "session_id": session_id,
    })
    response.set_cookie("sbar_session", session_id, httponly=True, samesite="lax", max_age=60 * 60 * 8)
    return response


@app.post("/api/view")
async def log_view(request: Request):
    body = await request.json()
    user = _user(request)
    insert_event(
        user_email=user.email, user_role=user.role_label,
        session_id=body["session_id"], sbar_id=body["sbar_id"],
        event_type="view",
        payload={"duration_seconds": body.get("duration_seconds", 0)},
    )
    return {"ok": True}


@app.post("/api/ask")
async def ask_question(request: Request, background: BackgroundTasks):
    body = await request.json()
    user = _user(request)
    question_id = str(uuid.uuid4())
    sbar_id = body.get("sbar_id")
    session_id = body["session_id"]
    question = body["question"]

    insert_event(
        user_email=user.email, user_role=user.role_label,
        session_id=session_id, sbar_id=sbar_id, event_type="question",
        payload={"question": question, "question_id": question_id},
    )

    _PENDING[question_id] = {"status": "running"}

    def _do_ask():
        try:
            result = ka_ask(question)
            insert_event(
                user_email=user.email, user_role=user.role_label,
                session_id=session_id, sbar_id=sbar_id, event_type="answer",
                payload={
                    "question_id": question_id,
                    "answer": result["answer"],
                    "sources": [s["filename"] for s in result["sources"]],
                    "low_confidence": result["low_confidence"],
                },
            )
            _PENDING[question_id] = {"status": "done", "result": result}
        except Exception as e:
            log.exception("KA call failed")
            _PENDING[question_id] = {"status": "error", "error": str(e)}

    background.add_task(_do_ask)
    return {"question_id": question_id}


@app.get("/api/answer/{question_id}")
async def get_answer(question_id: str):
    state = _PENDING.get(question_id)
    if state is None:
        raise HTTPException(status_code=404, detail="unknown question_id")
    return state


@app.post("/api/feedback")
async def feedback(request: Request):
    body = await request.json()
    user = _user(request)
    insert_event(
        user_email=user.email, user_role=user.role_label,
        session_id=body["session_id"], sbar_id=body.get("sbar_id"),
        event_type="feedback",
        payload={"question_id": body["question_id"], "rating": body["rating"]},
    )
    return {"ok": True}


@app.get("/author", response_class=HTMLResponse)
def author_view(request: Request, sbar_id: str | None = None):
    user = _user(request)
    if not user.is_author:
        return HTMLResponse("<h1>403 Not the SBAR author.</h1>", status_code=403)

    sbars = _list_sbars()
    sbar_id = sbar_id or (sbars[0]["id"] if sbars else None)
    if not sbar_id:
        return HTMLResponse("<h1>No SBARs published yet.</h1>")

    engagement_rows = query("""
        WITH per_user AS (
          SELECT user_email, user_role,
                 COUNT(*) FILTER (WHERE event_type='view')     AS views,
                 COUNT(*) FILTER (WHERE event_type='question') AS questions,
                 MAX(ts) AS last_event
          FROM sbar.audit_events
          WHERE sbar_id = %s
          GROUP BY user_email, user_role
        )
        SELECT * FROM per_user ORDER BY last_event DESC NULLS LAST
    """, (sbar_id,))

    question_rows = query("""
        SELECT q.user_role,
               q.payload->>'question'   AS question,
               q.payload->>'question_id' AS question_id,
               COALESCE((a.payload->>'low_confidence')::bool, false) AS low_confidence,
               COALESCE(NULLIF(f.payload->>'rating', ''), '') AS feedback,
               q.ts
        FROM sbar.audit_events q
        LEFT JOIN sbar.audit_events a
          ON a.session_id = q.session_id AND a.event_type='answer'
         AND a.payload->>'question_id' = q.payload->>'question_id'
        LEFT JOIN sbar.audit_events f
          ON f.session_id = q.session_id AND f.event_type='feedback'
         AND f.payload->>'question_id' = q.payload->>'question_id'
        WHERE q.event_type='question' AND q.sbar_id=%s
        ORDER BY q.ts DESC
    """, (sbar_id,))

    summary_row = query("""
        SELECT
          COUNT(DISTINCT user_email) FILTER (WHERE event_type='view')                   AS viewers,
          COUNT(DISTINCT user_email) FILTER (WHERE event_type='question')               AS askers,
          COUNT(*) FILTER (WHERE event_type='question')                                 AS questions,
          COUNT(*) FILTER (WHERE event_type='answer'
                           AND (payload->>'low_confidence')::bool = true)               AS unanswered
        FROM sbar.audit_events WHERE sbar_id=%s
    """, (sbar_id,))[0]

    title = next((s["title"] for s in sbars if s["id"] == sbar_id), sbar_id)
    return templates.TemplateResponse("author.html", {
        "request": request,
        "user": user,
        "sbar_id": sbar_id,
        "sbar_title": title,
        "all_sbars": sbars,
        "summary": summary_row,
        "engagement": engagement_rows,
        "questions": question_rows,
    })


# =============================================================================
# Auto-SBAR drafting flow
# =============================================================================

# In-process draft generation status keyed by draft_id.
_DRAFT_GEN: dict[str, dict] = {}


def _slugify(text: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "_", text.lower()).strip("_")
    return s[:60] or "untitled"


def _read_volume_text(volume_path: str, max_bytes: int = 200_000) -> str:
    """Read a UC volume file as text. Truncates at max_bytes to keep prompt
    sizes reasonable. Returns an empty string on any read failure."""
    try:
        resp = _workspace_client.files.download(volume_path)
        raw = resp.contents.read(max_bytes + 1)
        if len(raw) > max_bytes:
            return raw[:max_bytes].decode("utf-8", errors="replace") + "\n\n[truncated]"
        return raw.decode("utf-8", errors="replace")
    except Exception:
        log.exception(f"failed to read {volume_path}")
        return ""


@app.get("/author/drafts/new", response_class=HTMLResponse)
def new_draft_form(request: Request):
    user = _user(request)
    if not user.is_author:
        return HTMLResponse("<h1>403 Not the SBAR author.</h1>", status_code=403)
    return templates.TemplateResponse("author_draft_new.html", {"request": request, "user": user})


@app.post("/api/drafts")
async def create_draft(request: Request):
    body = await request.json()
    user = _user(request)
    if not user.is_author:
        raise HTTPException(status_code=403, detail="Not the SBAR author.")
    draft_id = drafts_lib.create_draft(
        author_email=user.email,
        title=body.get("title", "").strip() or "Untitled SBAR",
        audience=body.get("audience", "").strip() or "Executive Leadership Team",
        instruction=body.get("instruction", "").strip(),
    )
    insert_event(
        user_email=user.email, user_role=user.role_label,
        session_id=draft_id, sbar_id=None, event_type="draft_created",
        payload={"draft_id": draft_id, "title": body.get("title", ""),
                 "audience": body.get("audience", "")},
    )
    return {"draft_id": draft_id}


@app.post("/api/drafts/{draft_id}/upload")
async def upload_draft_source(draft_id: str, request: Request, file: UploadFile = File(...)):
    user = _user(request)
    if not user.is_author:
        raise HTTPException(status_code=403, detail="Not the SBAR author.")
    draft = drafts_lib.get_draft(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="draft not found")

    # Sanitize filename and write into the per-draft folder on the volume.
    raw_name = file.filename or "upload"
    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", raw_name)[:120]
    volume_path = f"{drafts_lib.draft_inputs_path(draft_id)}/{safe_name}"

    contents = await file.read()
    _workspace_client.files.upload(volume_path, io.BytesIO(contents), overwrite=True)
    drafts_lib.add_source_file(draft_id, safe_name, volume_path)

    return {"filename": safe_name, "volume_path": volume_path, "size": len(contents)}


@app.post("/api/drafts/{draft_id}/generate")
async def generate_draft_endpoint(draft_id: str, request: Request, background: BackgroundTasks):
    user = _user(request)
    if not user.is_author:
        raise HTTPException(status_code=403, detail="Not the SBAR author.")
    draft = drafts_lib.get_draft(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="draft not found")

    body = await request.json() if await request.body() else {}
    use_current_as_context = bool(body.get("regenerate", False))

    drafts_lib.set_status(draft_id, "generating", error_message=None)
    _DRAFT_GEN[draft_id] = {"status": "running"}

    insert_event(
        user_email=user.email, user_role=user.role_label,
        session_id=draft_id, sbar_id=None,
        event_type=("draft_regenerated" if use_current_as_context else "draft_generation_started"),
        payload={"draft_id": draft_id, "had_prior_edits": bool(draft.get("current_md")) and use_current_as_context},
    )

    def _run_generation():
        try:
            sources = []
            for src in (draft.get("source_files") or []):
                content = _read_volume_text(src["volume_path"])
                if content:
                    sources.append({"filename": src["filename"], "content": content})

            current_md = draft.get("current_md") if use_current_as_context else None

            result = generate_draft(
                author_email=user.email,
                instruction=draft.get("instruction") or "",
                title=draft.get("title") or "Untitled SBAR",
                audience=draft.get("audience") or "Executive Leadership Team",
                source_docs=sources,
                current_draft=current_md,
            )

            drafts_lib.update_draft_fields(
                draft_id,
                current_md=result["markdown"],
                corpus_searches=result["corpus_searches"],
                status="draft",
                error_message=None,
            )
            insert_event(
                user_email=user.email, user_role=user.role_label,
                session_id=draft_id, sbar_id=None,
                event_type="draft_generation_completed",
                payload={"draft_id": draft_id, "turns_used": result["turns_used"],
                         "corpus_search_count": len(result["corpus_searches"])},
            )
            _DRAFT_GEN[draft_id] = {"status": "done"}
        except Exception as e:
            log.exception("draft generation failed")
            drafts_lib.set_status(draft_id, "generation_failed", error_message=str(e))
            insert_event(
                user_email=user.email, user_role=user.role_label,
                session_id=draft_id, sbar_id=None,
                event_type="draft_generation_failed",
                payload={"draft_id": draft_id, "error": str(e)[:500]},
            )
            _DRAFT_GEN[draft_id] = {"status": "error", "error": str(e)}

    background.add_task(_run_generation)
    return {"status": "generating"}


@app.get("/author/drafts/{draft_id}", response_class=HTMLResponse)
def view_draft(request: Request, draft_id: str):
    user = _user(request)
    if not user.is_author:
        return HTMLResponse("<h1>403 Not the SBAR author.</h1>", status_code=403)
    draft = drafts_lib.get_draft(draft_id)
    if not draft:
        return HTMLResponse("<h1>404 draft not found</h1>", status_code=404)
    return templates.TemplateResponse("author_draft_edit.html", {
        "request": request, "user": user, "draft": draft,
    })


@app.get("/api/drafts/{draft_id}")
def get_draft_json(request: Request, draft_id: str):
    user = _user(request)
    if not user.is_author:
        raise HTTPException(status_code=403)
    draft = drafts_lib.get_draft(draft_id)
    if not draft:
        raise HTTPException(status_code=404)
    # Convert datetimes to iso strings so JSON serialization is happy.
    for k in ("created_at", "updated_at", "published_at"):
        if draft.get(k):
            draft[k] = draft[k].isoformat()
    return draft


@app.patch("/api/drafts/{draft_id}")
async def patch_draft(request: Request, draft_id: str):
    user = _user(request)
    if not user.is_author:
        raise HTTPException(status_code=403)
    body = await request.json()
    fields = {}
    if "current_md" in body:
        fields["current_md"] = body["current_md"]
        insert_event(
            user_email=user.email, user_role=user.role_label,
            session_id=draft_id, sbar_id=None, event_type="draft_edited",
            payload={"draft_id": draft_id, "length": len(body["current_md"])},
        )
    if "title" in body:
        fields["title"] = body["title"]
    if "audience" in body:
        fields["audience"] = body["audience"]
    if "instruction" in body:
        fields["instruction"] = body["instruction"]
    if not fields:
        return {"ok": True}
    drafts_lib.update_draft_fields(draft_id, **fields)
    return {"ok": True}


@app.post("/api/drafts/{draft_id}/publish")
async def publish_draft(request: Request, draft_id: str):
    user = _user(request)
    if not user.is_author:
        raise HTTPException(status_code=403)
    draft = drafts_lib.get_draft(draft_id)
    if not draft:
        raise HTTPException(status_code=404)
    md = draft.get("current_md")
    if not md:
        raise HTTPException(status_code=400, detail="draft has no markdown yet")

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    sbar_id = f"sbar_{today}_{_slugify(draft.get('title') or 'untitled')}"
    target_path = f"{SBAR_VOLUME_PATH}/{sbar_id}.md"

    _workspace_client.files.upload(target_path, io.BytesIO(md.encode("utf-8")), overwrite=False)

    drafts_lib.update_draft_fields(
        draft_id,
        status="published",
        published_at=datetime.now(timezone.utc),
        published_sbar_id=sbar_id,
    )
    insert_event(
        user_email=user.email, user_role=user.role_label,
        session_id=draft_id, sbar_id=sbar_id, event_type="draft_published",
        payload={"draft_id": draft_id, "sbar_id": sbar_id},
    )
    return {"sbar_id": sbar_id, "url": f"/sbar/{sbar_id}"}


@app.get("/api/source/{filename}", response_class=HTMLResponse)
def view_source(filename: str):
    """Serve a supplemental document so executives can click through citations.
    Reads from the supplemental_docs volume via the App SP. PDFs return as-is;
    markdown is rendered to HTML."""
    safe = re.sub(r"[^A-Za-z0-9._-]+", "", filename)
    if not safe or safe != filename:
        raise HTTPException(status_code=400, detail="invalid filename")

    supp_path = os.getenv("SUPP_VOLUME_PATH", "/Volumes/kk_test/sbar_briefing/supplemental_docs")
    full_path = f"{supp_path}/{safe}"
    try:
        resp = _workspace_client.files.download(full_path)
        raw = resp.contents.read()
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"source not found: {filename}")

    if filename.lower().endswith(".pdf"):
        from fastapi.responses import Response
        return Response(content=raw, media_type="application/pdf",
                        headers={"Content-Disposition": f'inline; filename="{safe}"'})

    text = raw.decode("utf-8", errors="replace")
    html = markdown.markdown(text, extensions=["tables", "fenced_code"])
    return HTMLResponse(f"""<!doctype html><html><head><meta charset='utf-8'>
<title>{safe}</title>
<link rel='stylesheet' href='/static/styles.css'>
<style>body{{padding:24px;max-width:900px;margin:0 auto;background:#fff;}}
.source-header{{padding-bottom:12px;margin-bottom:16px;border-bottom:1px solid var(--border);color:var(--muted);font-size:13px;}}
</style></head><body>
<div class='source-header'>Source document: <strong>{safe}</strong></div>
<div class='sbar-content'>{html}</div>
</body></html>""")


@app.get("/healthz")
def healthz():
    return {"ok": True}
