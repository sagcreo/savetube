import re
from enum import Enum
from dataclasses import dataclass


class Platform(Enum):
    YOUTUBE = "youtube"
    TIKTOK = "tiktok"


@dataclass
class ParsedURL:
    url: str
    platform: Platform


_YOUTUBE_RE = re.compile(
    r'https?://(?:www\.)?(?:youtube\.com/(?:watch\?v=|shorts/)|youtu\.be/)[\w\-]+'
)
_TIKTOK_RE = re.compile(
    r'https?://(?:www\.|vm\.)?tiktok\.com/\S+'
)


def extract_urls(text: str) -> list[ParsedURL]:
    cleaned = re.sub(r'<(https?://[^>|]+)(?:\|[^>]*)?>', r'\1', text)

    results: list[ParsedURL] = []
    seen: set[str] = set()

    for pattern, platform in [(_YOUTUBE_RE, Platform.YOUTUBE), (_TIKTOK_RE, Platform.TIKTOK)]:
        for match in pattern.finditer(cleaned):
            url = match.group(0).rstrip("/")
            if url not in seen:
                seen.add(url)
                results.append(ParsedURL(url=url, platform=platform))

    return results
