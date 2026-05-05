"""Notify executives when a new SBAR is published.

Two modes, configured via env vars:

  NOTIFICATION_SLACK_WEBHOOK_URL  - if set, POST a Slack-formatted message
                                    to that incoming webhook URL.
  (none of the above)             - log-only mode (the audit_events table
                                    still records that a notification
                                    "fired", which is useful for the demo
                                    and lets the author see in the dashboard
                                    that publish triggered the broadcast).

In production a customer typically wires this to whatever they already use
for executive communications: Slack, Teams (Teams accepts the same incoming
webhook shape), email via an internal mail service, or PagerDuty for the
"new board memo" use case.
"""
import os
import logging
import httpx

log = logging.getLogger(__name__)

WEBHOOK_URL = os.getenv("NOTIFICATION_SLACK_WEBHOOK_URL", "").strip()
EXEC_LIST = [e.strip() for e in os.getenv("NOTIFICATION_EXEC_LIST", "").split(",") if e.strip()]


def notify_published(*, title: str, author_email: str, sbar_id: str, app_url: str) -> dict:
    """Fire a publish notification. Returns an audit-friendly dict describing
    what happened so the caller can record it in audit_events."""
    sbar_url = f"{app_url.rstrip('/')}/sbar/{sbar_id}"
    summary = f"New SBAR published: *{title}* by {author_email} - {sbar_url}"

    audit = {
        "title": title,
        "sbar_id": sbar_id,
        "sbar_url": sbar_url,
        "channel": None,
        "recipients": EXEC_LIST,
        "delivered": False,
        "error": None,
    }

    if WEBHOOK_URL:
        audit["channel"] = "slack_webhook"
        try:
            payload = {
                "text": summary,
                "blocks": [
                    {"type": "section", "text": {"type": "mrkdwn", "text": summary}},
                    {"type": "context", "elements": [
                        {"type": "mrkdwn", "text": "Reply with thumbs up after reading. Open the link to ask follow-up questions in the briefing app."}
                    ]},
                ],
            }
            with httpx.Client(timeout=10) as client:
                r = client.post(WEBHOOK_URL, json=payload)
                r.raise_for_status()
            audit["delivered"] = True
            log.info(f"Slack notification delivered for {sbar_id}")
        except Exception as e:
            log.exception(f"Slack notification failed for {sbar_id}")
            audit["error"] = str(e)[:500]
    else:
        audit["channel"] = "log_only"
        audit["delivered"] = True  # the log emit itself is the delivery
        log.info(f"[NOTIFY-LOG-ONLY] {summary} (recipients={EXEC_LIST or '(none configured)'})")

    return audit
