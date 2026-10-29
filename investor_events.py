"""Grounded investor events, conservative date extraction and portable exports.

Publication dates are metadata only. Missing years are never filled in. Domain
provenance describes the URL; it does not independently confirm an event.
"""
from __future__ import annotations

import calendar
import csv
import hashlib
import html
import io
import re
import unicodedata
from datetime import date, datetime, timedelta, timezone
from difflib import SequenceMatcher
from urllib.parse import urlsplit


EVENT_TYPES = {
    "earnings": "Kết quả kinh doanh", "dividends": "Cổ tức",
    "issuance": "Phát hành cổ phiếu", "ownership": "Nội bộ / cổ đông lớn",
    "leadership": "Nhân sự lãnh đạo", "agm": "Đại hội cổ đông",
    "bonds": "Trái phiếu", "other": "Sự kiện khác",
}
MILESTONES = {
    "ex_rights": "Giao dịch không hưởng quyền", "record": "Đăng ký cuối cùng",
    "payment": "Thanh toán / chi trả", "meeting": "Họp cổ đông",
    "earnings_release": "Công bố kết quả kinh doanh", "issuance": "Phát hành",
    "subscription_end": "Hạn đăng ký mua", "bond_maturity": "Đáo hạn trái phiếu",
    "manual": "Mốc do bạn nhập",
}
STATUSES = {
    "announced": "Theo thông báo / bài nguồn", "expected": "Dự kiến",
    "scheduled": "Bạn đã lên lịch", "completed": "Đã diễn ra",
    "cancelled": "Đã hủy", "needs_review": "Cần kiểm tra",
}
_RULES = {
    "bonds": ("trai phieu", "bond", "debenture"),
    "dividends": ("co tuc", "dividend", "tam ung co tuc"),
    "issuance": ("phat hanh co phieu", "co phieu thuong", "chao ban co phieu", "esop", "share issuance", "rights issue"),
    "ownership": ("co dong lon", "nguoi noi bo", "giao dich noi bo", "dang ky mua", "dang ky ban", "insider", "major shareholder"),
    "leadership": ("bo nhiem", "mien nhiem", "tu nhiem", "chu tich", "tong giam doc", "ceo", "leadership"),
    "agm": ("dhdcd", "dai hoi dong co dong", "dai hoi co dong", "shareholder meeting", "agm"),
    "earnings": ("ket qua kinh doanh", "bao cao tai chinh", "bctc", "loi nhuan", "doanh thu", "earnings", "financial results"),
}
# No source-name or article-text claims are used to grant official provenance.
_EXCHANGE_DOMAINS = ("hsx.vn", "hose.vn", "hnx.vn", "vsd.vn", "vsdc.vn")
_ISSUER_DOMAINS = {
    "FPT": ("fpt.com", "fpt.com.vn"), "VNM": ("vinamilk.com.vn",),
    "HPG": ("hoaphat.com.vn",), "VIC": ("vingroup.net",),
    "VHM": ("vinhomes.vn",), "MWG": ("mwg.vn",),
    "SSI": ("ssi.com.vn",), "VCB": ("vietcombank.com.vn",),
}


def fold(text):
    text = unicodedata.normalize("NFD", str(text or "").lower().replace("đ", "d"))
    return "".join(char for char in text if unicodedata.category(char) != "Mn")


def safe_url(value):
    """Accept absolute HTTP(S) URLs, without credentials or control characters."""
    value = str(value or "").strip()
    if not value or re.search(r"[\x00-\x20\x7f\\]", value):
        return ""
    try:
        parts = urlsplit(value)
        if parts.scheme.lower() not in ("http", "https") or not parts.hostname:
            return ""
        if parts.username is not None or parts.password is not None:
            return ""
        _ = parts.port
    except ValueError:
        return ""
    return value


def article_tickers(article):
    raw = article.get("tickers") or article.get("ticker") or []
    if isinstance(raw, str):
        raw = re.split(r"[,;\s]+", raw)
    return sorted({str(t).strip().upper() for t in raw if str(t).strip()})


def official_source(url, tickers=()):
    url = safe_url(url)
    if not url:
        return False
    hostname = urlsplit(url).hostname.lower().rstrip(".")
    matches = lambda domain: hostname == domain or hostname.endswith("." + domain)
    if any(matches(domain) for domain in _EXCHANGE_DOMAINS):
        return True
    return any(matches(domain) for ticker in tickers
               for domain in _ISSUER_DOMAINS.get(str(ticker).upper(), ()))


def classify_event(article):
    # The headline is the strongest evidence for the principal event category.
    for text in (article.get("title", ""), article.get("article_text") or article.get("summary", "")):
        normalized = fold(text)
        scores = {kind: sum(bool(re.search(r"\b" + re.escape(term) + r"\b", normalized)) for term in terms)
                  for kind, terms in _RULES.items()}
        if re.search(r"\bthuong\b[^.;]{0,45}\bco phieu\b", normalized):
            scores["issuance"] += 2
        if max(scores.values(), default=0):
            return max(scores, key=scores.get)
    return "other"


def published_date(article):
    value = article.get("published_dt")
    if isinstance(value, datetime):
        return value.date().isoformat()
    try:
        return datetime.strptime(str(article.get("date", "")), "%d/%m/%Y").date().isoformat()
    except (TypeError, ValueError):
        return ""


def normalized_title(article):
    title = fold(article.get("title", ""))
    source = fold(article.get("source", "")).strip()
    if source:
        title = re.sub(r"\s+[-–—|]\s*" + re.escape(source) + r"\s*$", "", title)
    return " ".join(re.findall(r"[a-z0-9]+", title))


def stable_id(*values):
    return hashlib.sha256("\x1f".join(str(value) for value in values).encode("utf-8")).hexdigest()[:20]


def _same_event(left, right):
    a, b = normalized_title(left), normalized_title(right)
    if not a or not b:
        return False
    shared = set(article_tickers(left)) & set(article_tickers(right))
    day_a, day_b = published_date(left), published_date(right)
    if not day_a or not day_b or abs((date.fromisoformat(day_a) - date.fromisoformat(day_b)).days) > 2:
        return False
    if not shared:
        return bool(safe_url(left.get("url")) and left.get("url") == right.get("url") and a == b)
    if classify_event(left) != classify_event(right):
        return False
    # Different amounts, periods and dates are strong evidence of different events.
    if set(re.findall(r"\d+", a)) != set(re.findall(r"\d+", b)):
        return False
    if a == b:
        return True
    # An explicit identical bonus-share quantity is a stronger event anchor
    # than incidental headline wording; still require the same numeric facts.
    if classify_event(left) == "issuance":
        quantity = r"\b(\d+(?:\s+\d+)?\s+(?:trieu|ty)\s+co phieu thuong)\b"
        match_a, match_b = re.search(quantity, a), re.search(quantity, b)
        if match_a and match_b and match_a.group(1) == match_b.group(1):
            return True
    words_a, words_b = set(a.split()), set(b.split())
    overlap = len(words_a & words_b) / max(1, len(words_a | words_b))
    return min(len(words_a), len(words_b)) >= 6 and overlap >= .77 and SequenceMatcher(None, a, b).ratio() >= .88


def cluster_events(articles):
    """Complete-link grouping prevents a chain of weak matches merging events."""
    ordered = sorted(articles or [], key=lambda a: (published_date(a), normalized_title(a), str(a.get("url", ""))))
    groups = []
    for article in ordered:
        for group in groups:
            if all(_same_event(article, previous) for previous in group):
                group.append(article)
                break
        else:
            groups.append([article])
    clusters = []
    for group in groups:
        representative = group[0]
        tickers = sorted({ticker for article in group for ticker in article_tickers(article)})
        days = sorted({published_date(article) for article in group if published_date(article)})
        clusters.append({
            "id": stable_id(normalized_title(representative), ",".join(tickers), days[0] if days else ""),
            "title": str(representative.get("title", "")), "type": classify_event(representative),
            "tickers": tickers, "articles": group,
            "sources": sorted({str(article.get("source") or "Không rõ nguồn") for article in group}),
            "published_dates": days,
        })
    return sorted(clusters, key=lambda group: (group["published_dates"][-1:] or [""], group["id"]), reverse=True)


_ANCHORS = [
    ("ex_rights", r"(?:ngay\s+)?(?:giao dich khong huong quyen|gdkhq)|ex[- ]dividend(?: date)?"),
    ("record", r"(?:ngay\s+)?dang ky cuoi cung|(?:ngay\s+)?chot danh sach(?: co dong)?|record date"),
    ("payment", r"(?:ngay|thoi gian)\s+(?:thanh toan|chi tra)|(?:thanh toan|chi tra|tra)\s+co tuc|(?:thanh toan|chi tra)\s+(?:vao\s+)?ngay|(?:dividend\s+)?payment date"),
    ("meeting", r"dai hoi (?:dong )?co dong|dhdcd|hop co dong|shareholder meeting|annual general meeting|\bagm\b"),
    ("earnings_release", r"(?:ngay\s+)?cong bo\s+(?:bctc|bao cao tai chinh|ket qua kinh doanh)|earnings (?:release|publication)(?: date)?"),
    ("issuance", r"ngay phat hanh|thoi gian phat hanh|issuance date"),
    ("subscription_end", r"han (?:cuoi )?dang ky mua|ngay ket thuc dang ky mua|subscription deadline"),
    ("bond_maturity", r"ngay dao han|dao han trai phieu|maturity date"),
]
_ANCHOR_RE = re.compile("|".join(f"(?P<{kind}>{pattern})" for kind, pattern in _ANCHORS))
_DATE_RE = re.compile(
    r"(?<!\d)(?:(?P<iso_y>\d{4})-(?P<iso_m>\d{1,2})-(?P<iso_d>\d{1,2})"
    r"|(?P<d>\d{1,2})\s*[/.-]\s*(?P<m>\d{1,2})(?:\s*[/.-]\s*(?P<y>\d{4}|\d{2}))?"
    r"|(?:ngay\s+)(?P<word_d>\d{1,2})\s+thang\s+(?P<word_m>\d{1,2})(?:\s+(?:nam\s+)?(?P<word_y>\d{4}))?)(?!\d)"
)


def _date_value(match):
    values = match.groupdict()
    year = values.get("iso_y") or values.get("y") or values.get("word_y")
    if not year or len(year) != 4:
        return None, "Thiếu năm đầy đủ; không suy ra năm từ ngày đăng tin."
    day = values.get("iso_d") or values.get("d") or values.get("word_d")
    month = values.get("iso_m") or values.get("m") or values.get("word_m")
    try:
        value = date(int(year), int(month), int(day))
        if not 1900 <= value.year <= 2199:
            raise ValueError("unsupported year")
        return value.isoformat(), ""
    except ValueError:
        return None, "Ngày không hợp lệ; cần đối chiếu bài nguồn."


def extract_event_dates(article):
    """Only attach dates following a nearby explicit milestone in the same clause.

    Dates in reporting periods, headers and unrelated sentences never become
    calendar entries. This intentionally prefers review over guessing.
    """
    results, seen = [], set()
    texts = [article.get("title", ""), article.get("article_text") or article.get("summary", "")]
    for raw_text in texts:
        text = unicodedata.normalize("NFC", str(raw_text or ""))
        for sentence in re.split(r"(?:[!?;\n]+|(?<!\d)\.(?!\d))\s*", text):
            normalized = fold(sentence)
            anchors = list(_ANCHOR_RE.finditer(normalized))
            dates = list(_DATE_RE.finditer(normalized))
            for date_match in dates:
                candidates = [anchor for anchor in anchors if anchor.end() <= date_match.start()
                              and date_match.start() - anchor.end() <= 130]
                candidates = [anchor for anchor in candidates if not any(
                    anchor.end() <= other.start() < date_match.start() for other in dates)]
                if not candidates:
                    # Explicit inverted construction, e.g. “20/09/2026 là ngày đăng ký cuối cùng”.
                    following = [anchor for anchor in anchors if anchor.start() >= date_match.end()
                                 and re.fullmatch(r"\s*(?:la|is)\s*(?:ngay\s*)?", normalized[date_match.end():anchor.start()])]
                    if not following:
                        continue
                    anchor = following[0]
                else:
                    anchor = candidates[-1]
                bridge = normalized[anchor.end():date_match.start()] if anchor.end() <= date_match.start() else ""
                # Reporting-period dates, publication headers and other facts may
                # occur in the same sentence as an event, but are not its date.
                if re.search(r"(?:tinh den|tai ngay|so voi|cung ky|ket thuc (?:nam|quy)|du lieu|cap nhat|dang tin|ngay dang|ngay viet|bao cao ngay)", bridge):
                    continue
                if anchor.lastgroup == "meeting" and bridge and not re.search(r"(?:ngay|vao|dien ra|to chuc|du kien|on\b|scheduled|held)", bridge):
                    continue
                value, reason = _date_value(date_match)
                prefix = normalized[max(0, anchor.start() - 70):date_match.end()]
                expected = bool(re.search(r"\b(?:du kien|ke hoach|tam tinh|de xuat|expected|tentative|planned|proposed)\b", prefix))
                ambiguous = bool(re.search(r"\b(?:truoc|sau|khoang|cham nhat|khong muon hon|by|before|after|around)\b", bridge))
                if ambiguous:
                    reason, value = "Khoảng thời gian / hạn tương đối; cần chọn ngày chính xác sau khi đối chiếu.", None
                key = (anchor.lastgroup, value, date_match.group())
                if key in seen:
                    continue
                seen.add(key)
                results.append({"event_date": value, "milestone": anchor.lastgroup,
                                "status": "needs_review" if not value else ("expected" if expected else "announced"),
                                "evidence": sentence.strip(), "raw_date": date_match.group(), "review_reason": reason})
    return results


def build_calendar_events(articles, manual_events=()):
    dated, review = [], []
    for cluster in cluster_events(articles):
        entries = {}
        for article in cluster["articles"]:
            extracted = extract_event_dates(article)
            if not extracted:
                extracted = [{"event_date": None, "milestone": "manual", "status": "needs_review",
                              "evidence": str(article.get("title", "")), "raw_date": "",
                              "review_reason": "Chưa thấy ngày đầy đủ gắn trực tiếp với một mốc sự kiện."}]
            for candidate in extracted:
                key = (candidate["event_date"], candidate["milestone"], candidate["raw_date"] if not candidate["event_date"] else "")
                url = safe_url(article.get("url"))
                if key in entries:
                    if url and url not in entries[key]["source_urls"]:
                        entries[key]["source_urls"].append(url)
                    continue
                event = {**candidate, "id": stable_id(cluster["id"], *key), "cluster_id": cluster["id"],
                         "title": cluster["title"], "type": cluster["type"], "tickers": cluster["tickers"],
                         "source_url": url, "source_urls": [url] if url else [],
                         "source": str(article.get("source", "")), "published_date": published_date(article),
                         "official_source": official_source(url, article_tickers(article)), "origin": "news"}
                entries[key] = event
        for event in entries.values():
            (dated if event["event_date"] else review).append(event)
    for raw in manual_events or []:
        if not isinstance(raw, dict):
            continue
        try:
            event = validate_manual_event(raw)
        except ValueError:
            continue
        dated.append(event)
    return sorted(dated, key=lambda e: (e["event_date"], e["title"], e["id"])), review


def validate_manual_event(raw):
    title = str(raw.get("title") or "").strip()
    if not title:
        raise ValueError("Vui lòng nhập tên sự kiện.")
    try:
        event_date = date.fromisoformat(str(raw.get("event_date") or raw.get("date", "")))
        if not 1900 <= event_date.year <= 2199:
            raise ValueError()
    except ValueError:
        raise ValueError("Ngày sự kiện phải hợp lệ, có đủ năm (1900–2199).") from None
    url = str(raw.get("source_url") or "").strip()
    if url and not safe_url(url):
        raise ValueError("Nguồn phải là URL HTTP hoặc HTTPS hợp lệ.")
    kind = raw.get("type", "other")
    status = raw.get("status", "expected")
    if kind not in EVENT_TYPES or status not in STATUSES or status == "needs_review":
        raise ValueError("Loại hoặc trạng thái sự kiện không hợp lệ.")
    tickers = article_tickers(raw)
    if any(not re.fullmatch(r"[A-Z0-9][A-Z0-9._-]{0,19}", ticker) for ticker in tickers):
        raise ValueError("Mã chứng khoán chỉ dùng chữ, số, dấu chấm, gạch ngang hoặc gạch dưới.")
    return {"id": str(raw.get("id") or stable_id(title, event_date, ",".join(tickers), kind)),
            "event_date": event_date.isoformat(), "title": title[:500], "tickers": tickers,
            "type": kind, "status": status, "source_url": url, "source_urls": [url] if url else [],
            "official_source": official_source(url, tickers), "source": "Bạn nhập",
            "origin": "manual", "milestone": "manual", "published_date": "",
            "evidence": str(raw.get("evidence", ""))[:3000], "review_reason": ""}


def calendar_html(year, month, events):
    """Escaped, Monday-first month grid; no source string enters an attribute."""
    by_day = {}
    for event in events:
        try:
            when = date.fromisoformat(str(event.get("event_date", "")))
        except ValueError:
            continue
        if when.year == year and when.month == month:
            by_day.setdefault(when.day, []).append(event)
    cells = []
    for week in calendar.Calendar(firstweekday=0).monthdayscalendar(year, month):
        for day in week:
            if not day:
                cells.append('<div class="investor-day empty" role="gridcell"></div>')
                continue
            labels = []
            for event in by_day.get(day, [])[:3]:
                ticker = ", ".join(event.get("tickers", []))
                label = f'{ticker + " · " if ticker else ""}{MILESTONES.get(event.get("milestone"), EVENT_TYPES.get(event.get("type"), "Sự kiện"))}'
                if event.get("milestone") == "manual":
                    label = f'{ticker + " · " if ticker else ""}{event.get("title", "")}'
                if event.get("status") == "expected":
                    label += " (dự kiến)"
                if event.get("status") == "cancelled":
                    label += " (đã hủy)"
                labels.append(f'<div class="investor-day-event">{html.escape(label)}</div>')
            extra = max(0, len(by_day.get(day, [])) - 3)
            more = f'<div class="investor-day-more">+{extra} sự kiện</div>' if extra else ""
            cells.append(f'<div class="investor-day" role="gridcell"><strong>{day}</strong>{"".join(labels)}{more}</div>')
    return ('<style>.investor-calendar{display:grid;grid-template-columns:repeat(7,minmax(0,1fr));gap:5px;color:#262626;font-family:inherit}'
            '.investor-weekday{font-weight:700;padding:8px 4px;text-align:center}.investor-day{min-height:105px;padding:9px;background:#fdf8f3;border:1px solid #e5d6cf;border-radius:9px;overflow-wrap:anywhere}'
            '.investor-day.empty{opacity:.35}.investor-day-event{margin-top:6px;padding:4px 5px;background:#e4a4bd55;border-radius:4px;font-size:12px;line-height:1.35}.investor-day-more{font-size:11px;margin-top:4px}'
            '@media(max-width:640px){.investor-day{min-height:72px;padding:4px}.investor-day-event{font-size:10px;padding:2px}.investor-calendar{gap:2px}}</style>'
            f'<div class="investor-calendar" role="grid" aria-label="Lịch tháng {month}/{year}">'
            + ''.join(f'<div class="investor-weekday" role="columnheader">{day}</div>' for day in ("T2", "T3", "T4", "T5", "T6", "T7", "CN"))
            + ''.join(cells) + '</div>')


def events_csv(events):
    out = io.StringIO(newline="")
    writer = csv.writer(out)
    writer.writerow(["Ngày sự kiện", "Mã CK", "Tên sự kiện", "Loại", "Mốc", "Trạng thái", "Nguồn", "Xuất xứ", "Ngày đăng tin"])
    def cell(value):
        text = str(value or "")
        return "'" + text if text.lstrip().startswith(("=", "+", "-", "@")) or text.startswith(("\t", "\r", "\n")) else text
    for event in events:
        writer.writerow([cell(value) for value in (event.get("event_date"), ", ".join(event.get("tickers", [])),
                         event.get("title"), EVENT_TYPES.get(event.get("type"), "Sự kiện"),
                         MILESTONES.get(event.get("milestone"), ""), STATUSES.get(event.get("status"), ""),
                         safe_url(event.get("source_url")), "Bạn nhập" if event.get("origin") == "manual" else "Bài nguồn",
                         event.get("published_date"))])
    return ("\ufeff" + out.getvalue()).encode("utf-8")


def _ics_text(value):
    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n")
    text = "".join(c for c in text if c == "\n" or ord(c) >= 32)
    return text.replace("\\", "\\\\").replace("\n", "\\n").replace(";", "\\;").replace(",", "\\,")


def _fold_ics(line):
    lines, current, size = [], "", 0
    for char in line:
        count = len(char.encode("utf-8"))
        if size + count > 75:
            lines.append(current)
            current, size = " ", 1
        current += char
        size += count
    lines.append(current)
    return "\r\n".join(lines)


def events_ics(events, now=None):
    stamp = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Stock News AI//Investor Calendar//VI", "CALSCALE:GREGORIAN", "METHOD:PUBLISH"]
    for event in events:
        try:
            when = date.fromisoformat(str(event.get("event_date", "")))
            end = when + timedelta(days=1)
        except (ValueError, OverflowError):
            continue
        source = safe_url(event.get("source_url"))
        title = ", ".join(event.get("tickers", []))
        title = f'{title + " · " if title else ""}{event.get("title", "")}'
        provenance = "Tên miền nguồn chính thức" if event.get("official_source") else "Nguồn chưa được xác minh"
        description = "\n".join([MILESTONES.get(event.get("milestone"), ""), STATUSES.get(event.get("status"), ""),
                                 provenance, "Nguồn: " + source, "Ngày đăng tin: " + str(event.get("published_date") or "—"),
                                 str(event.get("evidence") or "")])
        lines += ["BEGIN:VEVENT", "UID:" + stable_id(event.get("id"), when, event.get("milestone")) + "@stock-news-ai.local",
                  "DTSTAMP:" + stamp, "DTSTART;VALUE=DATE:" + when.strftime("%Y%m%d"),
                  "DTEND;VALUE=DATE:" + end.strftime("%Y%m%d"), "SUMMARY:" + _ics_text(title),
                  "DESCRIPTION:" + _ics_text(description)]
        if source:
            lines.append("URL:" + source)
        if event.get("status") == "expected":
            lines.append("STATUS:TENTATIVE")
        elif event.get("status") == "cancelled":
            lines.append("STATUS:CANCELLED")
        lines.append("END:VEVENT")
    lines.append("END:VCALENDAR")
    return ("\r\n".join(_fold_ics(line) for line in lines) + "\r\n").encode("utf-8")
