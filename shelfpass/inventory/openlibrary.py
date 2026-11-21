"""Minimal Open Library client used to fill in book details.

Docs: https://openlibrary.org/dev/docs/api/search. Results are cached for a
day; any network problem returns an empty list so volunteers can keep typing
details by hand.
"""

from __future__ import annotations

import hashlib
import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass, field

from django.conf import settings
from django.core.cache import cache

from shelfpass.core.text import is_isbn_like, normalize_isbn
from shelfpass.facilities.vocab import guess_content_flags

logger = logging.getLogger(__name__)

SEARCH_FIELDS = "key,title,subtitle,author_name,isbn,publisher,first_publish_year,subject,cover_i"
CACHE_SECONDS = 60 * 60 * 24


class OpenLibraryError(Exception):
    """Raised for network or decoding problems; callers usually swallow it."""


@dataclass
class BookCandidate:
    title: str
    authors: str = ""
    isbn: str = ""
    publisher: str = ""
    year: int | None = None
    subjects: list[str] = field(default_factory=list)
    content_flags: list[str] = field(default_factory=list)
    cover_id: str = ""
    openlibrary_key: str = ""

    @property
    def cover_url(self) -> str:
        return f"https://covers.openlibrary.org/b/id/{self.cover_id}-M.jpg" if self.cover_id else ""

    def as_dict(self) -> dict:
        data = asdict(self)
        data["cover_url"] = self.cover_url
        return data


def _config(key: str):
    return settings.SHELFPASS[key]


def _fetch_json(url: str) -> dict:
    if not url.startswith(("https://", "http://")):
        raise OpenLibraryError("Only HTTP(S) URLs are supported")
    request = urllib.request.Request(  # noqa: S310 - scheme checked above
        url, headers={"User-Agent": _config("OPENLIBRARY_USER_AGENT"), "Accept": "application/json"}
    )
    try:
        with urllib.request.urlopen(request, timeout=_config("OPENLIBRARY_TIMEOUT")) as response:  # noqa: S310
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        raise OpenLibraryError(str(exc)) from exc


def _parse_doc(doc: dict, wanted_isbn: str = "") -> BookCandidate:
    isbns = [normalize_isbn(i) for i in doc.get("isbn", [])]
    isbns = [i for i in isbns if i]
    isbn = wanted_isbn if wanted_isbn and wanted_isbn in isbns else (isbns[0] if isbns else "")
    subjects = [str(s) for s in doc.get("subject", [])[:10]]
    title = str(doc.get("title", "")).strip()
    if doc.get("subtitle"):
        title = f"{title}: {doc['subtitle']}"
    return BookCandidate(
        title=title,
        authors="; ".join(doc.get("author_name", [])[:3]),
        isbn=isbn,
        publisher=str((doc.get("publisher") or [""])[0]),
        year=doc.get("first_publish_year"),
        subjects=subjects,
        content_flags=guess_content_flags(title, *subjects),
        cover_id=str(doc.get("cover_i") or ""),
        openlibrary_key=str(doc.get("key", "")),
    )


def search(query: str, limit: int = 8) -> list[BookCandidate]:
    """Search by free text or ISBN. Never raises; returns ``[]`` on failure."""
    query = (query or "").strip()
    if not query or not _config("OPENLIBRARY_ENABLED"):
        return []

    isbn = normalize_isbn(query) if is_isbn_like(query) else ""
    params = {"fields": SEARCH_FIELDS, "limit": str(limit)}
    if isbn:
        params["isbn"] = isbn
    else:
        params["q"] = query
    url = f"{_config('OPENLIBRARY_BASE_URL').rstrip('/')}/search.json?{urllib.parse.urlencode(params)}"

    cache_key = "openlibrary:" + hashlib.sha256(url.encode()).hexdigest()
    cached = cache.get(cache_key)
    if cached is not None:
        return [BookCandidate(**item) for item in cached]

    try:
        payload = _fetch_json(url)
    except OpenLibraryError as exc:
        logger.warning("Open Library lookup failed: %s", exc)
        return []

    results = [_parse_doc(doc, isbn) for doc in payload.get("docs", [])[:limit] if doc.get("title")]
    cache.set(cache_key, [asdict(r) for r in results], CACHE_SECONDS)
    return results
