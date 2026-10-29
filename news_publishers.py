"""Find publisher permalinks in public sitemaps when Google is unavailable."""
from functools import lru_cache
from datetime import datetime
from pathlib import Path
import json
import re
import time
import unicodedata
from urllib.parse import urlparse, unquote, urljoin
import xml.etree.ElementTree as ET

import requests
from bs4 import BeautifulSoup

ROOTS = {
    'cafef': ('https://cafef.vn/sitemap.xml',),
    'index.vn': ('https://index.vn/sitemap.xml',),
    'báo pháp luật việt nam': ('https://doanhnhan.baophapluat.vn/sitemaps.xml',
                              'https://baophapluat.vn/sitemap.xml'),
    'tin nhanh chứng khoán': ('https://www.tinnhanhchungkhoan.vn/sitemap.xml',),
    'vietstock': ('https://vietstock.vn/sitemap.xml',),
    'nguoiquansat.vn': ('https://nguoiquansat.vn/sitemap.xml',),
    'thuonghieucongluan.com.vn': ('https://thuonghieucongluan.com.vn/sitemap.xml',),
    'báo dân trí': ('https://dantri.com.vn/sitemap.xml',),
    'dantri.com.vn': ('https://dantri.com.vn/sitemap.xml',),
    'vietnamnet': ('https://vietnamnet.vn/sitemap.xml',),
    'báo vietnamnet': ('https://vietnamnet.vn/sitemap.xml',),
    'vnexpress': ('https://vnexpress.net/sitemap.xml',),
    'vnexpress.net': ('https://vnexpress.net/sitemap.xml',),
    'bnews.vn': ('https://bnews.vn/sitemap.xml',),
    'baodautu.vn': ('https://baodautu.vn/sitemap.xml',),
}
ROOTS['cafef.vn'] = ROOTS['cafef']
ROOTS['nhadautu.vn'] = ('https://nhadautu.vn/sitemap.xml',)
ROOTS['24hmoney'] = ('https://24hmoney.vn/sitemap.xml',)
ROOTS['tạp chí kinh tế chứng khoán việt nam'] = ('https://kinhtechungkhoan.vn/sitemap.xml',)
ROOTS['tạp chí kinh tế - tài chính online'] = ('https://tapchikinhtetaichinh.vn/sitemap.xml',)


def split_title(title):
    for publisher in sorted(ROOTS, key=len, reverse=True):
        suffix = ' - ' + publisher
        if title.casefold().endswith(suffix):
            return title[:-len(suffix)], publisher
    headline, _, publisher = title.rpartition(' - ')
    return headline, publisher.casefold()
HEADERS = {'User-Agent': 'Mozilla/5.0', 'Accept-Language': 'vi,en;q=0.8'}


def known_article(title, published_at=None):
    """Verified recent permalinks omitted from publishers' truncated catalogs.

    This stores links, not article content. Recheck title on every use and keep
    recurring headlines scoped to their publication date.
    """
    rows = json.loads(Path(__file__).with_name('news_source_links.json').read_text(encoding='utf-8'))
    for row in rows:
        if normalized(row['title']) != normalized(title):
            continue
        day = datetime.fromisoformat(str(published_at)).date() if published_at else datetime.now().date()
        published = datetime.fromisoformat(row['date']).date()
        if abs((day - published).days) > (1 if published_at else 30):
            continue
        try:
            r = requests.get(row['url'], headers=HEADERS, timeout=(5, 15))
            r.raise_for_status()
            soup = BeautifulSoup(r.content, 'html.parser')
            headline, _ = split_title(title)
            headings = [h.get_text(' ', strip=True) for h in soup.select('h1')]
            meta = soup.find('meta', property='og:title')
            if meta:
                headings.append(meta.get('content', ''))
            if same_host(r.url, row['url']) and any(normalized(h) == normalized(headline) for h in headings):
                return r.url, r.content
        except requests.RequestException:
            pass
    return None


def normalized(text):
    return re.sub(r'\W+', '', unicodedata.normalize('NFC', text).casefold())


def slug(text):
    text = unicodedata.normalize('NFKD', text.casefold().replace('đ', 'd'))
    return re.sub(r'[^a-z0-9]+', '-', ''.join(c for c in text if not unicodedata.combining(c))).strip('-')


def same_host(url, root):
    p = urlparse(url)
    return p.scheme in ('https', 'http') and not p.username and (p.hostname or '').removeprefix('www.') == (urlparse(root).hostname or '').removeprefix('www.')


@lru_cache(maxsize=96)
def _sitemap(url, bucket):
    # Cache successful public catalogs only; requests and parse failures can retry.
    r = requests.get(url, headers=HEADERS, timeout=(5, 12))
    r.raise_for_status()
    if len(r.content) > 8_000_000:
        raise ValueError('Sitemap too large')
    root = ET.fromstring(r.content)
    entries = []
    for node in root:
        values = {c.tag.rsplit('}', 1)[-1]: (c.text or '').strip() for c in node}
        location = values.get('loc', '')
        if not same_host(location, url):
            continue
        title = next((c.text or '' for c in node.iter() if c.tag.rsplit('}', 1)[-1] == 'title'), '')
        entries.append((location, values.get('lastmod', ''), title))
    return root.tag.rsplit('}', 1)[-1] == 'sitemapindex', entries


def _candidates(entries, headline):
    expected, title_slug = normalized(headline), slug(headline)
    matches = []
    for url, _, title in entries:
        path = slug(unquote(urlparse(url).path))
        words, path_words = set(title_slug.split('-')), set(path.split('-'))
        score = len(words & path_words) / max(1, len(words))
        if normalized(title) == expected or title_slug in path:
            score = 2
        if len(title_slug) >= 18 and score >= .65:
            matches.append((score, url))
    yield from (url for _, url in sorted(matches, reverse=True))


def publisher_catalog_article(title, published_at=None):
    """Return (verified URL, raw HTML), never a similar article or search page."""
    headline, publisher = split_title(title)
    if not headline:
        return None
    bucket = int(time.time() // 900)
    for root in ROOTS.get(publisher.casefold(), ()):
        queue, checked = [root], set()
        # Bound per-source work, favouring recent article archives over categories.
        while queue and len(checked) < 14:
            url = queue.pop(0)
            if url in checked:
                continue
            checked.add(url)
            try:
                is_index, entries = _sitemap(url, bucket)
                if is_index:
                    children = [e for e in entries if not re.search(r'categor|prices|sitemap-en|pages|topics|event|rss', e[0], re.I)]
                    def archive_date(entry):
                        date = re.search(r'(20\d{2})[-/](\d{1,2})(?:[-/](\d{1,2}))?', entry[0])
                        return '-'.join(f'{int(n):02d}' for n in date.groups(default='1')) if date else entry[1]
                    children.sort(key=archive_date, reverse=True)
                    if published_at:
                        day = datetime.fromisoformat(str(published_at)).date()
                        def priority(entry):
                            date = re.search(r'(20\d{2})[-/](\d{1,2})(?:[-/](\d{1,2})(?:-(\d{1,2}))?)?', entry[0])
                            if not date:
                                return 2
                            year, month, start, end = date.groups()
                            if int(year) == day.year and int(month) == day.month:
                                return 0 if not start or int(start) <= day.day <= int(end or start) else 3
                            return 4
                        children.sort(key=priority)
                    queue.extend(e[0] for e in children[:12])
                    continue
                for candidate in list(_candidates(entries, headline))[:2]:
                    response = requests.get(candidate, headers=HEADERS, timeout=(5, 15))
                    response.raise_for_status()
                    if not same_host(response.url, root):
                        continue
                    soup = BeautifulSoup(response.content, 'html.parser')
                    headings = [h.get_text(' ', strip=True) for h in soup.select('h1')]
                    meta = soup.select_one('meta[property="og:title"]')
                    if meta:
                        headings.append(meta.get('content', ''))
                    if any(normalized(h) == normalized(headline) for h in headings):
                        return candidate, response.content
            except (requests.RequestException, ET.ParseError, ValueError):
                continue
    return None


def disclosure_article(title):
    """Find the same exchange disclosure republished on CafeF's ticker page."""
    headline, _, publisher = title.rpartition(' - ')
    ticker = re.match(r'^([A-Z]{3}):', headline)
    if publisher.casefold() != 'vietstock' or not ticker:
        return None
    index = f'https://cafef.vn/du-lieu/{ticker[1].lower()}/thong-tin-chung.chn'
    try:
        response = requests.get(index, headers=HEADERS, timeout=(5, 15))
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')
        for a in soup.select('a[href]'):
            if normalized(a.get_text(' ', strip=True)) != normalized(headline):
                continue
            url = urljoin(index, a['href'])
            if same_host(url, index):
                response = requests.get(url, headers=HEADERS, timeout=(5, 15))
                response.raise_for_status()
                page = BeautifulSoup(response.content, 'html.parser')
                headings = [h.get_text(' ', strip=True) for h in page.select('h1')]
                meta = page.find('meta', property='og:title')
                if meta:
                    headings.append(meta.get('content', ''))
                if same_host(response.url, index) and any(normalized(h) == normalized(headline) for h in headings):
                    return response.url, response.content
    except requests.RequestException:
        pass
    return None
