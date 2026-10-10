"""What a link job says when it can't be fetched: what happened and what to do."""

UPDATE = "uv lock --upgrade-package yt-dlp --upgrade-package yt-dlp-ejs && uv sync"
REFUSED = (
    "sukoon takes links from YouTube, X, Facebook, Reddit, and SoundCloud. It also tries "
    "Instagram, TikTok, and Vimeo, which often turn it away. For anything else, download "
    "the file and drop it here."
)
PLAYLIST = "This link is a playlist or a channel. Paste the link of one video."
LIVE = "This is a live stream. Paste the link again once it has ended."
DRM = "This video is protected against copying (DRM), so it can't be fetched."
PRIVATE = "This video is private or was deleted, so it can't be fetched."
AGE = "This video is age-restricted, and sukoon never signs in, so it can't be fetched."
REGION = "This video isn't available in your region."
LOGIN = (
    "{name} only shares this video with signed-in people, and sukoon never signs in. "
    "Save it another way and drop the file here."
)
ELSEWHERE = "This post points to a video on another site. Open it there and paste that link."
NETWORK = "The connection dropped while fetching. Check your connection, then retry."
OUTDATED = (
    "yt-dlp couldn't read this {name} page. Its reader may be out of date, or {name} turned "
    "the request away. To update it, run: " + UPDATE
)
TURNED_AWAY = (
    "{name} turned the request away, as it does with many requests that don't come from a "
    "browser. Save the video another way and drop the file here."
)
STALLED = "The download made no progress for 10 minutes, so it was stopped."
CRASHED = "The download stopped unexpectedly."
STREAM = "This video is only offered as a kind of stream sukoon doesn't fetch."
SILENT = (
    "{name} sent this video without its sound, so there is nothing to clean. Some sites hold "
    "the sound back from people who aren't signed in."
)


def unexplained(detail: str) -> str:
    return f"Couldn't fetch this video. yt-dlp said: {detail}"


def too_long(max_seconds: float) -> str:
    return f"This video is longer than {max_seconds / 3600:g} hours, which is sukoon's limit."


def too_big(max_bytes: int) -> str:
    return f"This video is bigger than {max_bytes / 1024**3:g} GB, which is sukoon's limit."
