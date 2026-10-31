"""The office's portfolio at its own address's root (`/`), once published.

`/` belongs to no office (Unio's home is served there on every address), so this
looks the office up from the address itself. Unio's own address keeps its home,
and so does an office without the `portfolio` feature (A40) or with the
portfolio unpublished. `/?projeto={id}` shows one work with all its photos.
Signed-in staff see an unpublished portfolio with `/?previa=1`.

The page is plain HTML drawn here, with no script: quick to load, read by
search engines, and nothing to run in a visitor's browser.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from functools import cache
from html import escape
from pathlib import Path

from fastapi import Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select

from backend.db.isolation import scope_to_tenant
from backend.identity import sessions
from backend.office.models import OfficeProfile
from backend.office.profile import logo_urls
from backend.portfolio.models import Portfolio, PortfolioEntry, PortfolioPhoto
from backend.tenancy.models import Feature, Locale
from backend.tenancy.resolve import CurrentTenant, normalize_host, resolve
from backend.web.auth import COOKIE
from backend.web.portfolio import entries_with_photos, photo_url

log = logging.getLogger(__name__)
_CATALOGS = Path(__file__).resolve().parent.parent / "i18n"
HEADERS = {
    "Content-Security-Policy": (
        "default-src 'none'; style-src 'self'; img-src 'self'; "
        "base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
    ),
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "strict-origin-when-cross-origin",
}
PUBLISHED = {**HEADERS, "Cache-Control": "public, max-age=60"}
PREVIEW = {**HEADERS, "Cache-Control": "private, no-store", "X-Robots-Tag": "noindex"}


@cache
def _texts(locale: Locale) -> dict:
    return json.loads((_CATALOGS / f"{locale.value}.json").read_text("utf-8"))["portfolio"][
        "public"
    ]


def _fill(text: str, **values: object) -> str:
    """As the site's `t`: `{{name}}` filled in."""
    for name, value in values.items():
        text = text.replace("{{" + name + "}}", str(value))
    return text


def _paragraphs(text: str) -> str:
    return "".join(
        f"<p>{escape(part).replace(chr(10), '<br>')}</p>"
        for part in re.split(r"\n\s*\n", text.strip())
        if part.strip()
    )


def _whatsapp(number: str) -> str | None:
    digits = re.sub(r"\D", "", number)
    if len(digits) in (10, 11):  # a Brazilian number without the country code
        digits = "55" + digits
    return f"https://wa.me/{digits}" if len(digits) >= 12 else None


def _meta(entry: PortfolioEntry) -> str:
    return " · ".join(part for part in (entry.place, str(entry.year or "")) if part)


async def page(request: Request) -> HTMLResponse | None:
    """The portfolio for this address, or None: Unio's home is shown instead,
    also when the portfolio can't be read: the home never depends on the database."""
    try:
        return await _page(request)
    except Exception:
        log.exception("portfolio unavailable at %s; Unio's home shown", request.headers.get("host"))
        return None


async def _page(request: Request) -> HTMLResponse | None:
    settings = request.app.state.settings
    host = request.headers.get("host")
    if normalize_host(host) == settings.operator_host:
        return None
    async with request.app.state.sessionmaker() as session:
        resolution = await resolve(session, host)
    if resolution is None or not resolution.tenant.has(Feature.PORTFOLIO):
        return None
    tenant = resolution.tenant
    async with request.app.state.sessionmaker() as db:
        scope_to_tenant(db.sync_session, tenant.id)
        found = await db.scalar(select(Portfolio))
        preview = False
        if not (found and found.published):
            token = request.cookies.get(COOKIE)
            if "previa" not in request.query_params or not token:
                return None
            if await sessions.find_active(db, token) is None:
                return None
            await db.commit()
            preview = True
        office = await db.scalar(select(OfficeProfile))
        works = [(entry, photos) for entry, photos in await entries_with_photos(db) if photos]
        chosen = None
        wanted = request.query_params.get("projeto")
        if wanted:
            try:
                wanted_id = uuid.UUID(wanted)
            except ValueError:
                wanted_id = None
            chosen = next((work for work in works if work[0].id == wanted_id), None)
    document = _document(
        tenant, office, found.intro if found else "", works, chosen, preview, request
    )
    return HTMLResponse(document, headers=PREVIEW if preview else PUBLISHED)


def _document(
    tenant: CurrentTenant,
    office: OfficeProfile | None,
    intro: str,
    works: list[tuple[PortfolioEntry, list[PortfolioPhoto]]],
    chosen: tuple[PortfolioEntry, list[PortfolioPhoto]] | None,
    preview: bool,
    request: Request,
) -> str:
    t = _texts(tenant.locale)
    name = escape(office.display_name if office else tenant.name)
    keep = "previa=1" if preview else ""
    home = f"/?{keep}" if keep else "/"

    def link(entry: PortfolioEntry) -> str:
        return f"/?projeto={entry.id}" + (f"&amp;{keep}" if keep else "")

    light, dark = logo_urls(office)
    if light:
        source = (
            f'<source srcset="{escape(dark)}" media="(prefers-color-scheme: dark)">' if dark else ""
        )
        brand = f'<picture>{source}<img src="{escape(light)}" alt="{name}"></picture>'
    else:
        brand = f"<span>{name}</span>"

    if chosen:
        entry, photos = chosen
        title = f"{escape(entry.title)} · {name}"
        description = entry.description or intro
        meta = _meta(entry)
        figures = "".join(
            f'<figure><img src="{photo_url(photo)}?size=full" '
            f'alt="{escape(_fill(t["photo"], n=n, title=entry.title))}" '
            f'loading="{"eager" if n == 1 else "lazy"}" decoding="async"></figure>'
            for n, photo in enumerate(photos, start=1)
        )
        main = (
            f'<a class="back" href="{home}">← {escape(t["back"])}</a>'
            f'<article class="work"><header><h1>{escape(entry.title)}</h1>'
            + (f'<p class="meta">{escape(meta)}</p>' if meta else "")
            + "</header>"
            + (
                f'<div class="text">{_paragraphs(entry.description)}</div>'
                if entry.description
                else ""
            )
            + f'<div class="photos">{figures}</div></article>'
        )
        image = photo_url(photos[0])
    else:
        title = name
        description = intro
        cards = "".join(
            f'<li><a href="{link(entry)}"><img src="{photo_url(photos[0])}?size=card" alt="" '
            f'loading="{"eager" if n < 4 else "lazy"}" decoding="async">'
            f'<span class="title">{escape(entry.title)}</span>'
            + (f'<span class="meta">{escape(_meta(entry))}</span>' if _meta(entry) else "")
            + "</a></li>"
            for n, (entry, photos) in enumerate(works)
        )
        main = f'<section class="intro"><h1>{name}</h1>{_paragraphs(intro)}</section>' + (
            f'<section aria-labelledby="works"><h2 id="works" class="label">'
            f'{escape(t["works"])}</h2><ul class="works">{cards}</ul></section>'
            if works
            else f'<p class="empty">{escape(t["empty"])}</p>'
        )
        image = photo_url(works[0][1][0]) if works else None

    contact = []
    if office and office.contact_email:
        email = escape(office.contact_email)
        contact.append(f'<a href="mailto:{email}">{email}</a>')
    if office and office.whatsapp and (wa := _whatsapp(office.whatsapp)):
        contact.append(f'<a href="{wa}">WhatsApp {escape(office.whatsapp)}</a>')
    if office and office.phone:
        digits = re.sub(r"[^\d+]", "", office.phone)
        contact.append(f'<a href="tel:{digits}">{escape(office.phone)}</a>')
    if office and (office.address or office.city):
        place = ", ".join(part for part in (office.address, office.city) if part)
        contact.append(f"<span>{escape(place)}</span>")

    summary = escape(re.sub(r"\s+", " ", description).strip()[:200])
    origin = f"{request.url.scheme}://{request.headers.get('host', '')}"
    og_image = (
        f'<meta property="og:image" content="{escape(origin)}{image}?size=card">' if image else ""
    )
    banner = f'<p class="preview">{escape(t["preview"])}</p>' if preview else ""
    return f"""<!doctype html>
<html lang="{tenant.locale.value}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<meta name="description" content="{summary}">
<meta property="og:title" content="{title}">
<meta property="og:description" content="{summary}">
{og_image}
<link rel="stylesheet" href="/brand/portfolio.css">
</head>
<body>
{banner}
<header class="top wrap"><a class="brand" href="{home}">{brand}</a>
<nav><a href="#contato">{escape(t["contact"])}</a></nav></header>
<main class="wrap">{main}</main>
<footer id="contato" class="wrap">
<div><p class="label">{escape(t["contact"])}</p><p class="office">{name}</p>
<p class="ways">{"".join(contact)}</p></div>
<p class="small"><a href="/painel/">{escape(t["staff"])}</a></p>
</footer>
</body>
</html>
"""
