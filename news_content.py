"""Evidence-based summaries and a wrapping, accessible news table."""
import html
import json
import re
from urllib.parse import urlparse

from bs4 import BeautifulSoup


def clean_article_text(text):
    """Remove publisher UI/promotions from extracted, cached and AI text."""
    noise = re.compile(
        r"^(?:[#＃]\s*\S|bấm vào mỗi từ khóa|nhấn vào (?:mỗi )?từ khóa|"
        r"kết nối truyền thông cùng|cài đặt tiện ích|xem hdsd|"
        r"để theo dõi thị trường và mã chứng khoán mọi nơi|"
        r"tải (?:ứng dụng|app) 24hmoney|đọc thêm\s*[:：]|tin liên quan\s*[:：])", re.I)
    parts = re.split(r"\n+|(?<=[.!?])\s+(?=[A-ZÀ-Ỹ0-9\"“])", text)
    kept = [part.strip() for part in parts
            if part.strip() and not noise.search(re.sub(r"^\s*[-*•]\s+", "", part.strip()))]
    return text.strip() if len(kept) == len(parts) else "\n".join(kept)


def extract_article(document, title=""):
    soup = BeautifulSoup(document, "html.parser")
    structured = []

    def visit(value):
        if isinstance(value, dict):
            body = value.get("articleBody")
            if isinstance(body, str):
                structured.append(clean_article_text(BeautifulSoup(body, "html.parser").get_text("\n", strip=True)))
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    for script in soup.select('script[type="application/ld+json"]'):
        try:
            visit(json.loads(script.string or script.get_text()))
        except (ValueError, TypeError):
            pass
    for tag in soup.select("script, style, noscript, nav, aside, footer, .related-news, .related-articles, .item-term-policy"):
        tag.decompose()
    candidates = []
    for selector in ("#content_detail_news", "#explus-editor", ".KenhF_Content_News3", ".entry-body", ".article-detail-content", ".post-detail-body",
                     ".post-detail-body .ql-editor",
                     "[itemprop='articleBody']", ".article-editor", ".mekong-detail-body", ".article-body", ".article-content",
                     ".detail-content", ".content-detail", ".fck_detail", ".entry-content",
                     ".post-content", ".detail__content", ".news-content", "article"):
        if selector == "article" and candidates:
            continue
        for node in soup.select(selector):
            # 24HMoney's outer article container also contains tags and ads.
            # Prefer its actual body instead of choosing the larger wrapper.
            if selector in ('article', '.article-detail-content'):
                node = node.select_one('.news-content') or node
            # Keep facts in lists/tables as well as prose, without copying nested
            # paragraphs twice (a common publisher layout).
            blocks = node.select("p, li, tr, div.paragraph")
            paras = [p.get_text(" ", strip=True) for p in blocks
                     if not any(parent in blocks for parent in p.parents)]
            if selector == "article" and title:
                terms = set(re.findall(r"\w{3,}", re.sub(r"\s+-\s+[^-]+$", "", title).lower()))
                words = set(re.findall(r"\w{3,}", node.get_text(" ", strip=True).lower()))
                if (len(paras) < 3 and len(soup.select("article")) > 1) or len(terms & words) < max(2, len(terms)*.35):
                    continue
            text = "\n".join(p for p in paras if len(p) > 15)
            if not text:
                text = node.get_text(" ", strip=True)
            text = clean_article_text(text)
            if len(text) >= 180:
                candidates.append(text)
    if candidates:
        return max(candidates + structured, key=len)[:24000]
    if structured:
        return max(structured, key=len)[:24000]
    # A publisher description is still useful evidence; don't collect unrelated
    # page-wide paragraphs from navigation, sign-in or consent screens.
    description = soup.select_one('meta[property="og:description"], meta[name="description"]')
    text = description.get("content", "").strip() if description else ""
    if title and text:
        title_words = set(re.findall(r"\w{3,}", title.lower()))
        content_words = set(re.findall(r"\w{3,}", text.lower()))
        if len(title_words & content_words) < 2:
            return ""
    return clean_article_text(text)


def summary_sentences(item, detail=False, *, max_points=None, word_budget=None):
    title = re.sub(r"\s+-\s+[^-]+$", "", item.get("title", "")).strip()
    source = item.get("article_text") or item.get("summary") or title
    source = BeautifulSoup(source, "html.parser").get_text(" ", strip=True)
    source = clean_article_text(re.sub(r"[^\S\n]+", " ", source).strip())
    sentences = re.split(r"\n+|(?<=[.!?])\s+(?=[A-ZÀ-Ỹ0-9\"“])", source)
    unique, seen = [], set()
    for sentence in sentences:
        sentence = sentence.strip()
        key = re.sub(r"\W+", "", sentence.lower())
        if len(sentence) < 30 or key in seen:
            continue
        seen.add(key)
        unique.append(sentence)
    if not unique:
        return [title] if title else []

    # Keep the lead for context, then favour facts, dates and explanations.
    terms = ("doanh thu", "lợi nhuận", "cổ tức", "phát hành", "kỳ hạn", "lãi suất",
             "mục đích", "dự kiến", "so với", "do", "nhằm", "rủi ro", "ngày")
    ranked = sorted(range(1, len(unique)), key=lambda i: (
        -(2 * bool(re.search(r"\d", unique[i])) + sum(t in unique[i].lower() for t in terms)), i))
    limit, budget = ((16, 550) if len(source.split()) > 900 else (12, 400)) if detail else (4, 140)
    limit = max_points if max_points is not None else limit
    budget = word_budget if word_budget is not None else budget
    if detail:
        # Reserve coverage for context, plans and qualifications before filling
        # the remaining space with numeric facts. Output stays in source order.
        coverage = []
        for cues in (("do ", "nhờ", "nguyên nhân", "bối cảnh"),
                     ("dự kiến", "kế hoạch", "ngày", "thời hạn"),
                     ("rủi ro", "phụ thuộc", "tuy nhiên", "giả định", "chưa")):
            match = next((i for i in range(1, len(unique))
                          if any(cue in unique[i].lower() for cue in cues)), None)
            if match is not None:
                coverage.append(match)
        ranked = list(dict.fromkeys(coverage + ranked))
    selected, words = [0], len(unique[0].split())
    for i in ranked:
        count = len(unique[i].split())
        if len(selected) >= limit:
            break
        if words + count <= budget:
            selected.append(i)
            words += count
    result = [unique[i] for i in sorted(selected)]
    # Bound pathological single-sentence feeds without splitting words.
    if len(result[0].split()) > budget:
        result[0] = " ".join(result[0].split()[:budget]) + "…"
    return result


def _summary_source(item, ai_text=None):
    title = re.sub(r"\s+-\s+[^-]+$", "", item.get("title", "")).strip()
    normalize = lambda text: re.sub(r"\W+", "", text.casefold())
    source = ai_text or item.get("article_text") or item.get("summary", "")
    source = BeautifulSoup(source, "html.parser").get_text(" ", strip=True)
    source = clean_article_text(source)
    source = re.sub(r"(?m)^\s*(?:#{1,6}\s+|[-*•]\s+|\d+[.)]\s+)", "", source)
    source = source.replace("**", "")
    parts = re.split(r"\n+|(?<=[.!?])\s+(?=[A-ZÀ-Ỹ0-9\"“])", source)
    parts = [part.strip() for part in parts if normalize(part) not in
             {normalize(title), normalize(item.get("title", "")), ""}]
    return "\n".join(parts)


def summary_bullets(item, ai_text=None):
    """Only the main facts, at most eight points; never pad short sources."""
    source = _summary_source(item, ai_text)
    if not source or len(source.split()) < 8:
        return []
    return summary_sentences({"title": "", "article_text": source}, detail=True,
                             max_points=8, word_budget=220)


def summary_paragraph(item, ai_text=None):
    """Compact plain text for the exported table."""
    source = _summary_source(item, ai_text)
    if not source or len(source.split()) < 8:
        title = re.sub(r"\s+-\s+[^-]+$", "", item.get("title", "")).strip()
        return title or "Chưa tải được nội dung đủ để tóm tắt. Bạn có thể thử tải lại hoặc mở bài gốc."
    return " ".join(summary_sentences({"title": "", "article_text": source}))


def news_table(rows):
    """Natural row heights; summary gets most of the available width."""
    cells = []
    for index, row in enumerate(rows, start=1):
        esc = lambda key: html.escape(str(row[key]))
        title = html.escape(str(row.get('Tiêu đề bài báo', '')))
        cells.append(f'<tr><td data-label="Ngày / Mã" class="news-date"><strong>{esc("Mã CK")}</strong><br><span>{esc("Ngày")}</span></td>'
                     f'<td data-label="Tiêu đề bài báo">{title}<br><span class="small-muted">{esc("Loại tin")}</span></td>'
                     f'<td data-label="Tóm tắt"><a class="summary-jump" href="#news-detail-{index}" target="_self" title="Xem tóm tắt" aria-label="Xem tóm tắt tin {index}">↓</a></td></tr>')
    return ('<div class="news-table-wrap"><table class="news-table"><caption>Bảng tổng hợp tin chứng khoán</caption>'
            '<colgroup><col style="width:155px"><col><col style="width:85px"></colgroup>'
            '<thead><tr><th scope="col">Ngày / Mã</th><th scope="col">Tiêu đề bài báo / Loại tin</th>'
            '<th scope="col">Tóm tắt</th></tr></thead>'
            '<tbody>' + ''.join(cells) + '</tbody></table></div>')
