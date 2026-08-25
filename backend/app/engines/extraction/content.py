from dataclasses import dataclass

import trafilatura
from bs4 import BeautifulSoup


@dataclass(frozen=True, slots=True)
class ExtractedContent:
    title: str | None
    text: str | None


def extract_content(html: str, *, url: str) -> ExtractedContent:
    """Main-content extraction via trafilatura (strips nav/ads/boilerplate —
    master spec §72 "noise reduction"), with BeautifulSoup as a fallback for
    the title when trafilatura's own metadata pass doesn't find one."""
    text = trafilatura.extract(html, url=url, include_comments=False, include_tables=True)

    title: str | None = None
    metadata = trafilatura.extract_metadata(html)
    if metadata is not None:
        title = metadata.title

    if not title:
        soup = BeautifulSoup(html, "lxml")
        if soup.title and soup.title.string:
            title = soup.title.string.strip()

    return ExtractedContent(title=title, text=text)
