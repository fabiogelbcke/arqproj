"""The office's profiles on social networks, which the portfolio's footer links to.

Only addresses on the network itself are kept, so the public page never links
anywhere else.
"""

from __future__ import annotations

import re
from urllib.parse import urlsplit

from backend.portfolio.models import SocialNetwork

_HANDLE = re.compile(r"[A-Za-z0-9._-]{1,60}")


def _split(address: str):
    address = address.strip()
    if not re.match(r"^https?://", address, re.IGNORECASE):
        address = "https://" + address
    parts = urlsplit(address)
    host = (parts.hostname or "").lower().removeprefix("www.").removeprefix("m.")
    return host, [part for part in parts.path.split("/") if part], parts.query


# Each network's address, and where a bare "@name" leads there (None: nowhere,
# a LinkedIn page needs its whole address).
_NETWORKS: dict[SocialNetwork, tuple[str, str | None]] = {
    SocialNetwork.INSTAGRAM: ("instagram.com", "{}"),
    SocialNetwork.LINKEDIN: ("linkedin.com", None),
    SocialNetwork.PINTEREST: ("pinterest.com", "{}"),
    SocialNetwork.YOUTUBE: ("youtube.com", "@{}"),
    SocialNetwork.VIMEO: ("vimeo.com", "{}"),
    SocialNetwork.BEHANCE: ("behance.net", "{}"),
    SocialNetwork.FACEBOOK: ("facebook.com", "{}"),
    SocialNetwork.TIKTOK: ("tiktok.com", "@{}"),
}


def profile(network: SocialNetwork, value: str) -> str | None:
    """The profile's address on `network` ("@alinea" or any address there), or
    None if it isn't one."""
    domain, handle = _NETWORKS[network]
    value = value.strip()
    if value.startswith("@"):
        if handle is None or not _HANDLE.fullmatch(value[1:]):
            return None
        return f"https://www.{domain}/" + handle.format(value[1:])
    host, path, _query = _split(value)
    # Pinterest has an address per country (br.pinterest.com).
    if not (host == domain or host.endswith("." + domain)) or not path:
        return None
    if not all(re.fullmatch(r"[A-Za-z0-9._@%+-]{1,100}", part) for part in path):
        return None
    return f"https://www.{domain}/" + "/".join(path)
