"""Load publisher text behind RSS links without caching transient failures."""
import base64
import json
import re
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from news_content import extract_article


TIMEOUT = (5, 12)
MAX_BYTES = 3_000_000
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; MarketNotes/1.0)",
           "Accept-Language": "vi,en;q=0.8"}


class ArticleUnavailable(Exception):
    """No usable publisher content was returned; a later attempt may succeed."""


def _web_url(url):
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username:
        raise ArticleUnavailable("Invalid article URL")
    return url


def _is_google(url):
    host = urlparse(url).hostname or ""
    return host == "google.com" or host.endswith(".google.com")


def _request(session, method, url, **kwargs):
    """Bound both response size and network waits; retain raw encoding bytes."""
    with session.request(method, _web_url(url), timeout=TIMEOUT, stream=True, **kwargs) as response:
        response.raise_for_status()
        data = bytearray()
        for chunk in response.iter_content(chunk_size=65536):
            data.extend(chunk)
            if len(data) > MAX_BYTES:
                raise ArticleUnavailable("Article response is too large")
        return response.url, bytes(data)


def _legacy_target(token):
    # Older Google RSS IDs embed the publisher URL as a protobuf string.
    try:
        payload = base64.urlsafe_b64decode(token + "=" * (-len(token) % 4))
    except (ValueError, TypeError):
        return None
    match = re.search(rb'https?://[^\x00-\x20\x7f-\xff]+', payload)
    return match.group().decode("ascii") if match else None


def _rpc_target(document):
    # batchexecute is length-framed JSON with an anti-XSSI prefix.
    for line in document.decode("utf-8").splitlines():
        if not line.startswith("["):
            continue
        try:
            rows = json.loads(line)
            for row in rows:
                if isinstance(row, list) and len(row) > 2 and row[1] == "Fbv4je":
                    result = json.loads(row[2])
                    if result[0] == "garturlres" and isinstance(result[1], str):
                        return _web_url(result[1])
        except (ValueError, TypeError, IndexError):
            continue
    raise ArticleUnavailable("Google News did not return a publisher link")


def _resolve_google(session, url):
    parts = urlparse(url).path.rstrip("/").split("/")
    if len(parts) < 3 or parts[-2] not in {"articles", "read"}:
        raise ArticleUnavailable("Unsupported Google News link")
    token = parts[-1]
    if not re.fullmatch(r"[A-Za-z0-9_-]+", token):
        raise ArticleUnavailable("Invalid Google News article ID")
    legacy = _legacy_target(token)
    if legacy and not _is_google(legacy):
        return legacy

    final_url, document = _request(session, "GET", f"https://news.google.com/articles/{token}")
    if not _is_google(final_url):
        return final_url
    node = BeautifulSoup(document, "html.parser").select_one("[data-n-a-sg][data-n-a-ts]")
    if node is None:
        raise ArticleUnavailable("Google News resolution is temporarily unavailable")
    # Google's garturlreq protocol: https://github.com/SSujitX/google-news-url-decoder
    context = [["X", "X", ["X", "X"], None, None, 1, 1, "US:en", None, 1,
                None, None, None, None, None, 0, 1], "X", "X", 1, [1, 1, 1],
               1, 1, None, 0, 0, None, 0]
    call = ["garturlreq", context, token, int(node["data-n-a-ts"]), node["data-n-a-sg"]]
    batch = [[["Fbv4je", json.dumps(call), None, "generic"]]]
    _, reply = _request(session, "POST", "https://news.google.com/_/DotsSplashUi/data/batchexecute",
                        data={"f.req": json.dumps(batch)})
    target = _rpc_target(reply)
    if _is_google(target):
        raise ArticleUnavailable("Publisher link still points to Google")
    return target


def read_source_article(url, title=""):
    """Return extracted source text, or raise so Streamlit can retry failures."""
    try:
        _web_url(url)
        with requests.Session() as session:
            session.headers.update(HEADERS)
            session.max_redirects = 4
            target = _resolve_google(session, url) if urlparse(url).hostname == "news.google.com" else url
            final_url, document = _request(session, "GET", target)
            if _is_google(final_url):
                raise ArticleUnavailable("Publisher article was not reached")
            text = extract_article(document, title).strip()
            if len(text) < 180:
                raise ArticleUnavailable("Publisher returned too little article content")
            return text
    except (requests.RequestException, ValueError, TypeError, KeyError, UnicodeError) as exc:
        raise ArticleUnavailable("Could not load this source article") from exc


def gnewsdecoder(url, interval=1):
    """Compatibility adapter for the dashboard's existing resolver interface."""
    with requests.Session() as session:
        session.headers.update(HEADERS)
        session.max_redirects = 4
        return {'status': True, 'decoded_url': _resolve_google(session, _web_url(url))}
