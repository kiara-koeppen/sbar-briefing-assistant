"""Executive SBAR Briefing Assistant - FastAPI app.

Two surfaces:
  /                     Executive view - render current SBAR + chat with KA
  /author               Author view - engagement dashboard for the SBAR author

All KA interactions and SBAR views are logged to the Lakebase audit_events table.
"""
import os
import uuid
import json
import asyncio
import logging
import pathlib
from datetime import datetime, timezone

import markdown
from fastapi import FastAPI, Request, HTTPException, BackgroundTasks
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from lib.auth import current_user, CurrentUser
from lib.db import insert_event, query
from lib.ka import ask as ka_ask

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

APP_ROOT = pathlib.Path(__file__).parent
SBAR_VOLUME = pathlib.Path(os.getenv("SBAR_VOLUME_PATH", "/Volumes/kk_test/sbar_briefing/sbar_documents"))
AUTHOR_EMAILS = {e.strip() for e in os.getenv("AUTHOR_USER_EMAILS", "").split(",") if e.strip()}

app = FastAPI(title="SBAR Briefing Assistant")
app.mount("/static", StaticFiles(directory=APP_ROOT / "static"), name="static")
templates = Jinja2Templates(directory=APP_ROOT / "templates")


# In-process pending answers keyed by question_id.
# For demo single-replica simplicity. A multi-replica deploy would use Lakebase
# or Redis here; the audit table already captures the full record.
_PENDING: dict[str, dict] = {}


def _user(request: Request) -> CurrentUser:
    return current_user(request, AUTHOR_EMAILS)


def _list_sbars() -> list[dict]:
    files = sorted(SBAR_VOLUME.glob("*.md"))
    out = []
    for f in files:
        with open(f) as fh:
            first_line = fh.readline().strip().lstrip("# ").strip()
        out.append({
            "id": f.stem,
            "title": first_line,
            "modified": datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc).isoformat(),
        })
    out.sort(key=lambda x: x["modified"], reverse=True)
    return out


def _read_sbar(sbar_id: str) -> str:
    path = SBAR_VOLUME / f"{sbar_id}.md"
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"SBAR not found: {sbar_id}")
    return path.read_text()


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    user = _user(request)
    sbars = _list_sbars()
    if not sbars:
        return HTMLResponse("<h1>No SBARs published yet.</h1>", status_code=503)
    latest = sbars[0]
    return RedirectResponse(url=f"/sbar/{latest['id']}" + ("?author=1" if user.is_author else ""))


@app.get("/sbar/{sbar_id}", response_class=HTMLResponse)
def view_sbar(request: Request, sbar_id: str):
    user = _user(request)
    md = _read_sbar(sbar_id)
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


@app.get("/healthz")
def healthz():
    return {"ok": True}
