"""User identity from Databricks Apps OBO headers.

Databricks Apps proxies the executive's Databricks identity via two headers:
- X-Forwarded-User: their email
- X-Forwarded-Access-Token: their OAuth token (use to call workspace APIs ON BEHALF OF the user)

The service principal must NEVER be made an admin. All user-permission-sensitive
operations should use the OBO token via X-Forwarded-Access-Token.
"""
from dataclasses import dataclass
from fastapi import Request


@dataclass
class CurrentUser:
    email: str
    access_token: str | None
    is_author: bool

    @property
    def role_label(self) -> str:
        if self.is_author:
            return "Author"
        domain_role_map = {
            "ceo@": "CEO",
            "cfo@": "CFO",
            "coo@": "COO",
            "cmo@": "CMO",
            "cno@": "CNO",
            "board.chair@": "Board Chair",
        }
        for prefix, role in domain_role_map.items():
            if self.email.lower().startswith(prefix):
                return role
        return "Executive"


def current_user(request: Request, author_emails: set[str]) -> CurrentUser:
    email = request.headers.get("x-forwarded-email") or request.headers.get("x-forwarded-user", "")
    token = request.headers.get("x-forwarded-access-token")
    if not email:
        # Local-dev fallback: identify via env or default
        import os
        email = os.getenv("LOCAL_DEV_USER", "kiara.koeppen@databricks.com")
    is_author = email.lower() in {e.lower() for e in author_emails}
    return CurrentUser(email=email, access_token=token, is_author=is_author)
