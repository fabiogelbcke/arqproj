"""Unsubscribing from a project's emails (A32, plan section 14).

    GET  /api/emails/unsubscribe/{token}   the email's link: asks to confirm
    POST /api/emails/unsubscribe/{token}   confirmed, or the email program's own
                                           "unsubscribe" button (RFC 8058)

Opening the link only asks: mail scanners open links in emails, and that must not
unsubscribe anyone. The token names one address of one project, never expires, and
needs no sign-in. Once unsubscribed, the address gets nothing more from that project,
and staff can't undo it (the Projeto dialog shows it as such).
"""

from __future__ import annotations

import logging
from html import escape

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.engine import get_tenant_session
from backend.notifications.digest import unsubscribing
from backend.notifications.models import ProjectRecipient, RecipientStatus
from backend.notifications.texts import t
from backend.projects.models import Project
from backend.tenancy.resolve import CurrentTenant, current_tenant

log = logging.getLogger(__name__)
router = APIRouter(include_in_schema=False)

_HEADERS = {
    "Cache-Control": "no-store",
    "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",  # the token is in the address
}


def _page(tenant: CurrentTenant, title: str, body: str, status: int = 200) -> HTMLResponse:
    return HTMLResponse(
        f'<!doctype html><html lang="{tenant.locale.value}"><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{escape(title)}</title>"
        '<body style="font: 16px/1.5 system-ui, sans-serif; max-width: 32rem; margin: 15vh auto;'
        f' padding: 0 16px">{body}</body></html>',
        status_code=status,
        headers=_HEADERS,
    )


async def _target(request: Request, token: str, db: AsyncSession):
    """The project (of this office) and the address a token names, with the
    address's row if it is still listed."""
    found = unsubscribing(request.app.state.settings, token)
    if found is None:
        return None
    project_id, email = found
    project = await db.scalar(select(Project.name).where(Project.id == project_id))
    if project is None:  # another office's, or gone
        return None
    recipient = await db.scalar(
        select(ProjectRecipient).where(
            ProjectRecipient.project_id == project_id, ProjectRecipient.email == email
        )
    )
    return project_id, email, project, recipient


def _invalid(tenant: CurrentTenant) -> HTMLResponse:
    text = t(tenant.locale, "unsubscribeInvalid")
    return _page(tenant, text, f"<p>{escape(text)}</p>", 404)


@router.get("/api/emails/unsubscribe/{token}")
async def ask(
    request: Request,
    token: str,
    tenant: CurrentTenant = Depends(current_tenant),
    db: AsyncSession = Depends(get_tenant_session),
) -> HTMLResponse:
    found = await _target(request, token, db)
    if found is None:
        return _invalid(tenant)
    _project_id, email, project, recipient = found
    title = t(tenant.locale, "unsubscribeTitle", project=project)
    if recipient is not None and recipient.status is RecipientStatus.UNSUBSCRIBED:
        done = t(tenant.locale, "unsubscribed", email=email, project=project)
        return _page(tenant, title, f"<p>{escape(done)}</p>")
    ask_text = t(tenant.locale, "unsubscribeAsk", email=email, project=project)
    button = escape(t(tenant.locale, "unsubscribeConfirm"))
    return _page(
        tenant,
        title,
        f"<h1 style='font-size:1.25rem'>{escape(title)}</h1><p>{escape(ask_text)}</p>"
        f'<form method="post"><button type="submit" style="font: inherit; padding: 10px 18px">'
        f"{button}</button></form>",
    )


@router.post("/api/emails/unsubscribe/{token}")
async def confirm(
    request: Request,
    token: str,
    tenant: CurrentTenant = Depends(current_tenant),
    db: AsyncSession = Depends(get_tenant_session),
) -> HTMLResponse:
    found = await _target(request, token, db)
    if found is None:
        return _invalid(tenant)
    project_id, email, project, recipient = found
    if recipient is None:
        # Removed by staff meanwhile: kept as unsubscribed, so adding it back
        # can't override the client's choice.
        db.add(
            ProjectRecipient(
                project_id=project_id, email=email, status=RecipientStatus.UNSUBSCRIBED
            )
        )
        await db.commit()
    elif recipient.status is not RecipientStatus.UNSUBSCRIBED:
        recipient.status = RecipientStatus.UNSUBSCRIBED
        await db.commit()
    log.info("emails: an address unsubscribed from project %s", project_id)
    done = t(tenant.locale, "unsubscribed", email=email, project=project)
    return _page(
        tenant, t(tenant.locale, "unsubscribeTitle", project=project), f"<p>{escape(done)}</p>"
    )
