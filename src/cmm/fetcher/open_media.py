"""Helpers shared by providers of openly licensed media."""
from __future__ import annotations

import re
from html.parser import HTMLParser
from urllib.parse import urlparse


class _TextParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)


def plain_text(value: str) -> str:
    parser = _TextParser()
    parser.feed(str(value or ""))
    return " ".join(" ".join(parser.parts).split())


def media_url(value: str) -> str:
    value = str(value or "").strip()
    parsed = urlparse(value)
    return value if parsed.scheme in {"https", "http"} and parsed.netloc else ""


def license_code(name: str, url: str = "") -> str:
    """Recognize known licenses; never infer public-domain status from missing data."""
    url = media_url(url).lower()
    parsed = urlparse(url)
    if parsed.hostname in {"creativecommons.org", "www.creativecommons.org"}:
        if parsed.path.startswith("/publicdomain/zero/"):
            return "cc0"
        if parsed.path.startswith("/publicdomain/mark/"):
            return "pdm"
        match = re.match(r"/licenses/(by(?:-nc)?(?:-sa|-nd)?)/", parsed.path)
        if match:
            return match.group(1)
    normalized = plain_text(name).lower().strip()
    if normalized in {"cc0", "cc0 1.0", "public domain", "public domain mark", "pdm"}:
        return "cc0" if normalized.startswith("cc0") else "pdm"
    match = re.fullmatch(r"(?:cc[ -])?(by(?:-nc)?(?:-sa|-nd)?)(?:[ /]+\d+(?:\.\d+)?)?", normalized)
    return match.group(1) if match else "unknown"


def attribution_text(title: str, creator: str, code: str, source_page: str, version: str = "") -> str:
    return " · ".join(part for part in [plain_text(title), plain_text(creator), " ".join([code.upper(), version]).strip(), source_page] if part)
