import re
import urllib.parse

_RESERVED = re.compile(r'[<>:"/\\|?*\x00-\x1f\x7f]')
MAX_STEM = 150
SUFFIX = " (no music)"


def download_name(original: str, ext: str) -> str:
    """The name a finished file is offered under. The app never stores files by it; `clean` does."""
    stem = original.rsplit(".", 1)[0] if "." in original else original
    stem = _RESERVED.sub("-", stem).rstrip(". ")[:MAX_STEM].rstrip(". ")
    return f"{stem or 'sukoon'}{SUFFIX}.{ext}"


def content_disposition(name: str) -> str:
    """RFC 6266 header: an ASCII fallback for old clients plus the exact UTF-8 name."""
    fallback = "".join(c if 32 <= ord(c) < 127 and c not in '"\\' else "-" for c in name)
    quoted = urllib.parse.quote(name, safe="")
    return f"attachment; filename=\"{fallback}\"; filename*=UTF-8''{quoted}"
