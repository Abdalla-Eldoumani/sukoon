"""The sites sukoon takes links from, and the check every link passes before anything is fetched."""

import ipaddress
import urllib.request
from typing import Any
from urllib.parse import urlsplit

from sukoon.links.messages import REFUSED

# Each accepted site, and the yt-dlp extractor family allowed to read it.
SITES = {
    "youtube.com": "youtube",
    "youtu.be": "youtube",
    "x.com": "twitter",
    "twitter.com": "twitter",
    "instagram.com": "instagram",
    "tiktok.com": "tiktok",
    "facebook.com": "facebook",
    "fb.watch": "facebook",
    "reddit.com": "reddit",
    "v.redd.it": "reddit",
    "vimeo.com": "vimeo",
    "soundcloud.com": "soundcloud",
}
NAMES = {
    "youtube": "YouTube",
    "twitter": "X",
    "instagram": "Instagram",
    "tiktok": "TikTok",
    "facebook": "Facebook",
    "reddit": "Reddit",
    "vimeo": "Vimeo",
    "soundcloud": "SoundCloud",
}
# No yt-dlp reader handles these short links; they redirect to one that does.
SHORT = {"fb.watch", "v.redd.it"}


class LinkRefused(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def site(url: str) -> str:
    """The accepted site a link belongs to (youtube.com for www.youtube.com); raises LinkRefused.

    Only plain https links to the listed hosts or their subdomains: no user part, no port, no
    raw addresses, no look-alike letters.
    """
    try:
        parts = urlsplit(url.strip())
        port = parts.port
    except ValueError:
        raise LinkRefused(REFUSED) from None
    host = parts.hostname or ""
    if parts.scheme != "https" or parts.username is not None or port is not None:
        raise LinkRefused(REFUSED)
    if not host.isascii() or _is_address(host):
        raise LinkRefused(REFUSED)
    for name in SITES:
        if host == name or host.endswith(f".{name}"):
            return name
    raise LinkRefused(REFUSED)


def site_or_blank(url: str) -> str:
    try:
        return site(url)
    except LinkRefused:
        return ""


def _is_address(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return False
    return True


def resolve_short(url: str) -> str:
    """Follows a short link to the page it stands for, refusing any hop off the accepted sites."""

    class StayOnSite(urllib.request.HTTPRedirectHandler):
        def redirect_request(
            self, req: Any, fp: Any, code: int, msg: str, headers: Any, newurl: str
        ) -> Any:
            site(newurl)
            return super().redirect_request(req, fp, code, msg, headers, newurl)

    opener = urllib.request.build_opener(StayOnSite)
    request = urllib.request.Request(url, headers={"user-agent": "Mozilla/5.0"})  # noqa: S310
    with opener.open(request, timeout=30) as response:
        final: str = response.geturl()
    site(final)
    return final
