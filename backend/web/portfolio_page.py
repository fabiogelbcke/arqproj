"""The office's portfolio at its own address's root (`/`), once published.

`/` belongs to no office (Unio's home is served there on every address), so this
looks the office up from the address itself. Unio's own address keeps its home,
and so does an office without the `portfolio` feature (A40) or with the
portfolio unpublished. `/?projeto={id}` shows one work with all its photos.
Signed-in staff see an unpublished portfolio with `/?previa=1`.

The page is plain HTML drawn here: quick to load and read by search engines.
One small script of ours, `portfolio.js`, adds the carousel's arrows and opens
photos and videos large over the page; without it, the carousel still scrolls
and each opens on its own. Videos, from the office's storage like the photos,
play only there, in the browser's own player.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import uuid
from collections.abc import Callable
from datetime import date
from decimal import Decimal
from functools import cache
from html import escape
from pathlib import Path

from fastapi import Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy import select

from backend.db.isolation import scope_to_tenant
from backend.identity import sessions
from backend.office.models import OfficeProfile
from backend.office.profile import logo_urls
from backend.portfolio.models import (
    Portfolio,
    PortfolioEntry,
    PortfolioFormat,
    PortfolioPhoto,
    PortfolioVideo,
    SocialNetwork,
)
from backend.projects.enums import DetailType
from backend.projects.models import ProjectTypeDef
from backend.tenancy.middleware import REDIRECT_MAX_AGE, redirect_url
from backend.tenancy.models import Feature, Locale
from backend.tenancy.resolve import CurrentTenant, normalize_host, resolve
from backend.web.auth import COOKIE
from backend.web.portfolio import (
    SheetLineOut,
    details_by_entry,
    entries_with_photos,
    links,
    photo_url,
    video_url,
    videos_by_entry,
)
from backend.web.portfolio_icons import ICON_PATHS

log = logging.getLogger(__name__)
_CATALOGS = Path(__file__).resolve().parent.parent / "i18n"
_PUBLIC = Path(__file__).with_name("public")  # served by home.py at /brand/
HEADERS = {
    "Content-Security-Policy": (
        "default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self'; "
        "media-src 'self'; "
        "base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
    ),
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "strict-origin-when-cross-origin",
}
REDIRECT_HEADERS = {"Cache-Control": f"public, max-age={REDIRECT_MAX_AGE}"}
PUBLISHED = {**HEADERS, "Cache-Control": "public, max-age=60"}
Works = list[tuple[PortfolioEntry, list[PortfolioPhoto]]]
Label = Callable[[PortfolioEntry], str]
PREVIEW = {**HEADERS, "Cache-Control": "private, no-store", "X-Robots-Tag": "noindex"}


@cache
def _texts(locale: Locale) -> dict:
    texts = json.loads((_CATALOGS / f"{locale.value}.json").read_text("utf-8"))["portfolio"]
    return {
        **texts["public"],
        "types": texts["types"],
        "statuses": texts["statuses"],
        "networks": texts["networks"],
    }


@cache
def _fingerprint(name: str) -> str:
    return hashlib.sha256((_PUBLIC / name).read_bytes()).hexdigest()[:12]


def _asset_url(name: str, deployed: bool) -> str:
    """`/brand/<name>` with the file's fingerprint, so a browser holding the old
    file (cached for an hour) asks for the new one as soon as the page changes.
    Locally, the file is read each time: it changes without a restart."""
    if not deployed:
        _fingerprint.cache_clear()
    return f"/brand/{name}?v={_fingerprint(name)}"


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


def _area(area: Decimal, locale: Locale) -> str:
    """As people write it: "1.250 m²", "85,5 m²" (in English "1,250 m²")."""
    written = f"{area:,.2f}".rstrip("0").rstrip(".")
    if locale is Locale.PT_BR:
        written = written.translate(str.maketrans(",.", ".,"))
    return f"{written} m²"


def _fact(line: SheetLineOut, locale: Locale) -> str:
    """A line of the work's sheet as the page writes it: an area in m², a date
    the way the language writes one ("02/03/2026", in English "03/02/2026"), text as typed."""
    if line.type is DetailType.AREA:
        return _area(Decimal(line.value), locale)
    if line.type is DetailType.DATE:
        when = date.fromisoformat(line.value)
        return when.strftime("%d/%m/%Y" if locale is Locale.PT_BR else "%m/%d/%Y")
    return line.value


def _title(text: str) -> str:
    """Escaped, and never broken onto a new line before a dash ("Apartamento
    Atlântico — Copacabana" breaks after it, not before)."""
    return re.sub(r" ([—–-]) ", "\u00a0\\1 ", escape(text))


def _size(item: PortfolioPhoto | PortfolioVideo) -> str:
    """`width` and `height` for an image's tag, so the page lays it out at its
    shape before it loads; nothing for a file whose size isn't known."""
    return f' width="{item.width}" height="{item.height}"' if item.width and item.height else ""


def _loading(first: bool) -> str:
    """The first image fetched at once, the others as they come into view."""
    return 'fetchpriority="high"' if first else 'loading="lazy"'


def _tall(photo: PortfolioPhoto) -> bool:
    """An upright photo (a post, a story): shown whole where a landscape cover
    would be cropped."""
    return bool(photo.width and photo.height and photo.height > photo.width)


def _cover_img(photo: PortfolioPhoto, alt: str, attributes: str) -> str:
    """A cover filling a landscape frame; an upright one whole, over a blurred
    copy of itself (the frame's element gets the `tall` class)."""
    backdrop = (
        f'<img class="backdrop" src="{photo_url(photo)}?size=card" alt="" aria-hidden="true">'
        if _tall(photo)
        else ""
    )
    return f'{backdrop}<img src="{photo_url(photo)}?size=full" alt="{alt}" {attributes}>'


def _meta(entry: PortfolioEntry) -> str:
    return " · ".join(part for part in (entry.place, str(entry.year or "")) if part)


async def page(request: Request) -> Response | None:
    """The portfolio for this address, or None: Unio's home is shown instead,
    also when the portfolio can't be read: the home never depends on the database."""
    try:
        return await _page(request)
    except Exception:
        log.exception("portfolio unavailable at %s; Unio's home shown", request.headers.get("host"))
        return None


async def _page(request: Request) -> Response | None:
    settings = request.app.state.settings
    host = request.headers.get("host")
    if normalize_host(host) == settings.operator_host:
        return None
    async with request.app.state.sessionmaker() as session:
        resolution = await resolve(session, host)
    if resolution is None or not resolution.tenant.has(Feature.PORTFOLIO):
        return None
    if resolution.redirect_host:
        # An alias or `www.`: to the office's own address first, as every other
        # path is (the photos and logo would be redirected there, off this page).
        target = redirect_url(request.scope, host, resolution.redirect_host, settings.deployed)
        return RedirectResponse(target, status_code=301, headers=REDIRECT_HEADERS)
    tenant = resolution.tenant
    async with request.app.state.sessionmaker() as db:
        scope_to_tenant(db.sync_session, tenant.id)
        found = await db.scalar(select(Portfolio))
        preview = False
        if not (found and found.published):
            token = request.cookies.get(COOKIE)
            if "previa" not in request.query_params or not token:
                return None
            signed_in = await sessions.find_active(db, token)
            # Confirmed staff only, as everywhere else (an account from the shared
            # office link has a session before its email is confirmed).
            if signed_in is None or signed_in[1].email_confirmed_at is None:
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
        videos = (await videos_by_entry(db)).get(chosen[0].id, []) if chosen else []
        sheet = (await details_by_entry(db, tenant.locale)).get(chosen[0].id, []) if chosen else []
        kinds = list(await db.scalars(select(ProjectTypeDef).order_by(ProjectTypeDef.position)))
    types = _type_labels(kinds, tenant.locale)
    document = _document(
        tenant, office, found, works, chosen, videos, sheet, types, preview, request
    )
    return HTMLResponse(document, headers=PREVIEW if preview else PUBLISHED)


def _type_labels(kinds: list[ProjectTypeDef], locale: Locale) -> dict[str, str]:
    """The public label of each of the site's project types, in the dashboard's
    order: a short word for the built-in ones ("Arquitetura", not "Projeto
    Arquitetônico"), a type the operator added by its own name (A44)."""
    short = _texts(locale)["types"]

    def own(kind: ProjectTypeDef) -> str:
        return kind.labels.get(locale.value) or kind.labels[Locale.PT_BR.value]

    return {kind.key: short.get(kind.key) or own(kind) for kind in kinds}


def _document(
    tenant: CurrentTenant,
    office: OfficeProfile | None,
    found: Portfolio | None,
    works: Works,
    chosen: tuple[PortfolioEntry, list[PortfolioPhoto]] | None,
    videos: list[PortfolioVideo],
    sheet: list[SheetLineOut],
    types: dict[str, str],
    preview: bool,
    request: Request,
) -> str:
    t = {**_texts(tenant.locale), "types": types}
    deployed = request.app.state.settings.deployed
    intro = found.intro if found else ""
    mosaic = found is not None and found.format is PortfolioFormat.MOSAIC
    name = escape(office.display_name if office else tenant.name)
    keep = "previa=1" if preview else ""
    home = f"/?{keep}" if keep else "/"

    def link(entry: PortfolioEntry) -> str:
        return f"/?projeto={entry.id}" + (f"&amp;{keep}" if keep else "")

    def kind(entry: PortfolioEntry) -> str:
        return types.get(entry.project_type or "", "")

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
        # Type, place and year are on the cover, with the title; the sheet below
        # it: its lines in the office's order, then where the work stands.
        facts = "".join(
            f"<div><dt>{escape(label)}</dt><dd>{escape(value)}</dd></div>"
            for label, value in (
                *((line.label, _fact(line, tenant.locale)) for line in sheet),
                (t["status"], t["statuses"].get(entry.status or "", "")),
            )
            if value
        )
        index = next(n for n, work in enumerate(works) if work[0].id == entry.id)
        following = works[(index + 1) % len(works)] if len(works) > 1 else None
        after = ""
        if following:
            upcoming, upcoming_photos = following
            after = (
                f'<a class="following" href="{link(upcoming)}">'
                f'<img src="{photo_url(upcoming_photos[0])}?size=card" alt="" loading="lazy">'
                f'<span><span class="label">{escape(t["nextWork"])}</span>'
                f'<span class="title">{_title(upcoming.title)}</span></span></a>'
            )
        back = f'<a class="back" href="{home}#projetos">← {escape(t["back"])}</a>'
        heading = (
            (f'<p class="label">{escape(kind(entry))}</p>' if kind(entry) else "")
            + f"<h1>{_title(entry.title)}</h1>"
            + (f'<p class="meta">{escape(_meta(entry))}</p>' if _meta(entry) else "")
        )
        if mosaic:
            # The title above the images, each in its own shape, in a grid.
            main = (
                f'<article class="work mosaic-work"><header class="post-head wrap">{back}{heading}'
                '</header><div class="wrap">'
                + _about(facts, entry.description)
                + _posts(t, entry, photos, videos)
                + f"</div></article>{after}"
            )
        else:
            main = (
                # The cover across the page, darkened toward its edges so the title,
                # the work's type, place and year and the way back read over it.
                f'<article class="work"><header class="hero{" tall" if _tall(photos[0]) else ""}">'
                f'<a class="cover zoom" href="{photo_url(photos[0])}?size=full" '
                f'aria-label="{escape(_fill(t["open"], n=1))}">'
                + _cover_img(
                    photos[0],
                    escape(_fill(t["photo"], n=1, title=entry.title)),
                    'fetchpriority="high"',
                )
                + f'</a><div class="hero-top wrap">{back}</div><div class="hero-text wrap">'
                + heading
                + '</div></header><div class="wrap">'
                + _about(facts, entry.description)
                + _gallery(t, entry, photos, videos)
                + f"</div></article>{after}"
            )
        image = photo_url(photos[0])
    else:
        title = name
        description = intro
        main = ("" if mosaic else _carousel(t, works, link, kind)) + (
            f'<section class="intro wrap" id="escritorio">{_paragraphs(intro)}</section>'
            if intro.strip()
            else ""
        )
        main += _works(t, works, link, kind, keep, request.query_params.get("tipo"), mosaic)
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
    # The office's networks: their marks beside the page's sections at the top,
    # and with their names in the footer. Discreet (the page's own colour, the
    # text's size), but seen on arriving and on leaving.
    profiles = list(links(found).items())

    def mark(network: str) -> str:
        return (
            '<svg viewBox="0 0 24 24" aria-hidden="true">'
            f'<path d="{ICON_PATHS[SocialNetwork(network)]}"></path></svg>'
        )

    follow = (
        '<div class="follow">'
        + "".join(
            f'<a href="{escape(address)}" rel="noopener" '
            f'aria-label="{escape(t["networks"][network])}">{mark(network)}</a>'
            for network, address in profiles
        )
        + "</div>"
        if profiles
        else ""
    )
    social = (
        f'<div><p class="label">{escape(t["follow"])}</p><p class="nets">'
        + "".join(
            f'<a href="{escape(address)}" rel="noopener">{mark(network)}'
            f"<span>{escape(t['networks'][network])}</span></a>"
            for network, address in profiles
        )
        + "</p></div>"
        if profiles
        else ""
    )

    summary = escape(re.sub(r"\s+", " ", description).strip()[:200])
    origin = f"{request.url.scheme}://{request.headers.get('host', '')}"
    og_image = (
        f'<meta property="og:image" content="{escape(origin)}{image}?size=card">' if image else ""
    )
    banner = f'<p class="preview">{escape(t["preview"])}</p>' if preview else ""
    office_link = (
        f'<a href="{home}#escritorio">{escape(t["office"])}</a>'
        if intro.strip() and not chosen
        else ""
    )
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
<link rel="stylesheet" href="{_asset_url("portfolio.css", deployed)}">
<script src="{_asset_url("portfolio.js", deployed)}" defer></script>
</head>
<body>
{banner}
<header class="top wrap"><a class="brand" href="{home}">{brand}</a>
<nav><a href="{home}#projetos">{escape(t["works"])}</a>{office_link}\
<a href="#contato">{escape(t["contact"])}</a></nav>{follow}</header>
<main>{main}</main>
<footer id="contato" class="wrap">
<div><p class="label">{escape(t["contact"])}</p><p class="office">{name}</p>
<p class="ways">{"".join(contact)}</p></div>
{social}
<p class="small"><a href="/painel/">{escape(t["staff"])}</a></p>
</footer>
</body>
</html>
"""


CAROUSEL_MAX = 8


def _about(facts: str, description: str) -> str:
    """The work's sheet (its details, where it stands) beside its text, as architecture
    sites set them: the sheet narrow on the left, the text in a reading measure."""
    if not facts and not description.strip():
        return ""
    return (
        f'<section class="about{"" if facts else " solo"}">'
        + (f'<dl class="facts">{facts}</dl>' if facts else "")
        + (f'<div class="text">{_paragraphs(description)}</div>' if description.strip() else "")
        + "</section>"
    )


def _gallery(
    t: dict, entry: PortfolioEntry, photos: list[PortfolioPhoto], videos: list[PortfolioVideo]
) -> str:
    """The work's videos and other photos, small, side by side; a video by its
    poster with a play mark. Each opens large over the page, the cover too, and
    the arrows go through them all; a video plays only there (`portfolio.js`;
    without it, each opens on its own)."""
    label = escape(_fill(t["gallery"], title=entry.title))
    films = "".join(
        f'<li><a class="zoom film" href="{video_url(video)}" '
        f'data-poster="{video_url(video)}/poster" '
        f'aria-label="{escape(_fill(t["watch"], n=n))}">'
        f'<img src="{video_url(video)}/poster?size=card" '
        f'alt="{escape(_fill(t["video"], n=n, title=entry.title))}" '
        'loading="lazy" decoding="async"><span class="play" aria-hidden="true"></span></a></li>'
        for n, video in enumerate(videos, start=1)
    )
    figures = "".join(
        f'<li><a class="zoom" href="{photo_url(photo)}?size=full" '
        f'aria-label="{escape(_fill(t["open"], n=n))}">'
        f'<img src="{photo_url(photo)}?size=card" '
        f'alt="{escape(_fill(t["photo"], n=n, title=entry.title))}" '
        f'loading="lazy" decoding="async"></a></li>'
        for n, photo in enumerate(photos[1:], start=2)
    )
    credits = (
        f'<p class="credits">{escape(_fill(t["credits"], names=entry.credits))}</p>'
        if entry.credits
        else ""
    )
    items = f'<ul class="photos">{films}{figures}</ul>' if films or figures else ""
    gallery = (
        f'<section class="gallery" aria-label="{label}">{items}{credits}</section>'
        if items or credits
        else ""
    )
    return gallery + _lightbox(t, label)


def _posts(
    t: dict, entry: PortfolioEntry, photos: list[PortfolioPhoto], videos: list[PortfolioVideo]
) -> str:
    """The mosaic format's work: its videos, then all its photos (the cover too), as
    a grid of images each in its own shape, like a profile on the networks; each
    opens large over the page like the gallery's. The grid is the mosaic's
    (`mosaic`, laid out by `portfolio.js`), in the order the photos were added."""
    label = escape(_fill(t["gallery"], title=entry.title))
    films = "".join(
        f'<li><a class="zoom film" href="{video_url(video)}" '
        f'data-poster="{video_url(video)}/poster" '
        f'aria-label="{escape(_fill(t["watch"], n=n))}">'
        f'<img src="{video_url(video)}/poster?size=card" '
        f'alt="{escape(_fill(t["video"], n=n, title=entry.title))}"{_size(video)} '
        f'{_loading(n == 1)} decoding="async">'
        '<span class="play" aria-hidden="true"></span></a></li>'
        for n, video in enumerate(videos, start=1)
    )
    figures = "".join(
        f'<li><a class="zoom" href="{photo_url(photo)}?size=full" '
        f'aria-label="{escape(_fill(t["open"], n=n))}">'
        f'<img src="{photo_url(photo)}?size=card" '
        f'alt="{escape(_fill(t["photo"], n=n, title=entry.title))}"{_size(photo)} '
        f'{_loading(n == 1 and not videos)} decoding="async">'
        "</a></li>"
        for n, photo in enumerate(photos, start=1)
    )
    credits = (
        f'<p class="credits">{escape(_fill(t["credits"], names=entry.credits))}</p>'
        if entry.credits
        else ""
    )
    return (
        f'<section class="gallery" aria-label="{label}">'
        f'<ul class="mosaic posts">{films}{figures}</ul>{credits}</section>' + _lightbox(t, label)
    )


def _lightbox(t: dict, label: str) -> str:
    return (
        f'<dialog class="lightbox" aria-label="{label}">'
        '<img alt=""><video controls playsinline hidden></video>'
        '<p class="count" aria-live="polite"></p>'
        f'<button type="button" class="close" aria-label="{escape(t["close"])}">×</button>'
        f'<button type="button" class="prev" aria-label="{escape(t["previous"])}">←</button>'
        f'<button type="button" class="next" aria-label="{escape(t["next"])}">→</button>'
        "</dialog>"
    )


def _carousel(t: dict, works: Works, link: Label, kind: Label) -> str:
    """The first works, one cover each, side by side: swiped on a phone, scrolled
    with the arrows `portfolio.js` adds (without it, the strip still scrolls)."""
    shown = works[:CAROUSEL_MAX]
    if not shown:
        return ""
    total = len(shown)
    slides = "".join(
        f'<li class="slide{" tall" if _tall(photos[0]) else ""}" '
        f'aria-label="{escape(_fill(t["slide"], n=n, total=total))}">'
        f'<a href="{link(entry)}">'
        + _cover_img(photos[0], "", _loading(n == 1) + ' decoding="async"')
        + '<span class="caption">'
        + (f'<span class="label">{escape(kind(entry))}</span>' if kind(entry) else "")
        + f'<span class="title">{_title(entry.title)}</span>'
        + (f'<span class="meta">{escape(_meta(entry))}</span>' if _meta(entry) else "")
        + "</span></a></li>"
        for n, (entry, photos) in enumerate(shown, start=1)
    )
    controls = (
        f'<div class="controls" hidden><span class="count" aria-hidden="true">'
        f"<b>01</b> / {total:02d}</span>"
        f'<button type="button" class="prev" aria-label="{escape(t["previous"])}">←</button>'
        f'<button type="button" class="next" aria-label="{escape(t["next"])}">→</button></div>'
        if total > 1
        else ""
    )
    return (
        f'<section class="carousel" aria-roledescription="carousel" '
        f'aria-label="{escape(t["carousel"])}"><ul class="track" tabindex="0">{slides}</ul>'
        f"{controls}</section>"
    )


def _works(
    t: dict, works: Works, link: Label, kind: Label, keep: str, wanted: str | None, mosaic: bool
) -> str:
    """The works under the menu of types: a grid of covers cropped to one frame,
    or, in the mosaic format, every cover in its own shape. Every work
    is in the page, those of other types hidden, so the menu switches types in
    place (`portfolio.js`); without the script its links reload the page."""
    if not works:
        return f'<p class="empty wrap">{escape(t["empty"])}</p>'
    present = [key for key in t["types"] if any(e.project_type == key for e, _ in works)]
    wanted = wanted if wanted in present else None
    menu = ""
    if len(present) > 1:
        extra = f"&amp;{keep}" if keep else ""

        def item(key: str | None, label: str) -> str:
            href = (f"/?tipo={key}{extra}" if key else (f"/?{keep}" if keep else "/")) + "#projetos"
            current = ' aria-current="page"' if key == wanted else ""
            return f'<li><a href="{href}"{current}>{escape(label)}</a></li>'

        menu = (
            f'<nav class="types" aria-label="{escape(t["menu"])}"><ul>'
            + item(None, t["all"])
            + "".join(item(key, t["types"][key]) for key in present)
            + "</ul></nav>"
        )

    def _about(entry: PortfolioEntry) -> str:
        return " · ".join(part for part in (kind(entry), _meta(entry)) if part)

    def cover(photo: PortfolioPhoto) -> str:
        image = (
            f'<img src="{photo_url(photo)}?size=card" alt=""{_size(photo) if mosaic else ""} '
            'loading="lazy" decoding="async">'
        )
        return image if mosaic else f'<span class="frame">{image}</span>'

    cards = "".join(
        f"<li{'' if wanted in (None, entry.project_type) else ' hidden'} "
        f'data-type="{escape(entry.project_type or "")}">'
        f'<a href="{link(entry)}">{cover(photos[0])}'
        f'<span class="title">{_title(entry.title)}</span>'
        + (f'<span class="meta">{escape(_about(entry))}</span>' if _about(entry) else "")
        + "</a></li>"
        for entry, photos in works
    )
    return (
        f'<section class="projects wrap" id="projetos" aria-labelledby="works">'
        f'<div class="projects-head"><h2 id="works">{escape(t["works"])}</h2>{menu}</div>'
        f'<ul class="{"mosaic" if mosaic else "works"}">{cards}</ul></section>'
    )
