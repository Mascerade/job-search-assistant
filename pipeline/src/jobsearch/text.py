"""Turn posting HTML into readable plain text."""

from __future__ import annotations

import html as html_lib
import re

from bs4 import BeautifulSoup

MAX_CHARS = 20_000


def html_to_text(raw: str | None) -> str | None:
    if not raw:
        return None
    # Greenhouse returns HTML that is itself entity-escaped ("&lt;p&gt;").
    if "&lt;" in raw and "<" not in raw:
        raw = html_lib.unescape(raw)
    soup = BeautifulSoup(raw, "html.parser")
    for li in soup.find_all("li"):
        li.insert_before("\n• ")
    for tag in soup.find_all(["p", "div", "br", "h1", "h2", "h3", "h4", "ul", "ol", "tr"]):
        tag.insert_before("\n")
    text = soup.get_text()
    text = html_lib.unescape(text).replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text[:MAX_CHARS] or None
