"""Investor event radar and calendar UI."""
from datetime import date
import html
import streamlit as st
from investor_events import (EVENT_TYPES, MILESTONES, STATUSES, cluster_events,
                            build_calendar_events, calendar_html, events_csv, events_ics,
                            validate_manual_event, safe_url)


def source_link(label, url):
    if safe_url(url):
        st.markdown(f'<a href="{html.escape(url, quote=True)}" target="_blank" rel="noopener noreferrer">{html.escape(label)} ↗</a>', unsafe_allow_html=True)


def render_event_radar(articles, profile):
    st.markdown("### Những sự kiện đáng theo dõi.")
    st.caption("Tin được phân loại theo sự kiện chính trong tiêu đề. Chỉ gom những bài có đủ dấu hiệu trùng nhau; số nguồn không phải điểm xác nhận độ chính xác.")
    groups = cluster_events(articles)
    codes = sorted({t for g in groups for t in g["tickers"]})
    c1, c2 = st.columns(2)
    selected = c1.multiselect("Mã cần xem", codes, key="event_codes")
    types = c2.multiselect("Loại sự kiện", list(EVENT_TYPES), format_func=EVENT_TYPES.get, key="event_types")
    visible = [g for g in groups if (not selected or set(selected) & set(g["tickers"])) and (not types or g["type"] in types)]
    m1, m2, m3 = st.columns(3)
    m1.metric("Sự kiện sau khi gom", len(visible))
    m2.metric("Bài nguồn", sum(len(g["articles"]) for g in visible))
    m3.metric("Doanh nghiệp", len({t for g in visible for t in g["tickers"]}))
    if not visible:
        st.info("Quét tin ở tab Stock News hoặc thay bộ lọc để xem sự kiện.")
    for group in visible:
        with st.expander(f'{EVENT_TYPES[group["type"]]} · {group["title"]} ({len(group["articles"])} bài)'):
            st.caption(", ".join(group["tickers"]) + " · " + ", ".join(group["published_dates"]))
            for a in group["articles"]:
                st.write(a["title"])
                st.caption(f'{a.get("source", "")} · {a.get("published", a.get("date", ""))}')
                if safe_url(a.get("url")):
                    source_link("Đối chiếu bài nguồn", a["url"])


def render_event_calendar(articles, profile):
    st.markdown("### Những ngày cần nhớ.")
    st.caption("Lịch lấy mốc có ngày, tháng, năm rõ ràng từ tin đã quét. Ngày đăng báo không được dùng làm ngày sự kiện. Đối chiếu nguồn trước khi sử dụng.")
    dated, review = build_calendar_events(articles, profile["manual_events"])
    today = date.today()
    a, b, c = st.columns([1, 1, 2])
    year = a.number_input("Năm", 2000, 2199, today.year, key="calendar_year")
    month = b.selectbox("Tháng", list(range(1, 13)), index=today.month-1, key="calendar_month")
    ticker = c.multiselect("Lọc mã trong lịch", sorted({t for e in dated for t in e["tickers"]}), key="calendar_codes")
    events = [e for e in dated if (not ticker or set(ticker) & set(e["tickers"])) and e["event_date"].startswith(f"{year:04d}-{month:02d}")]
    st.markdown(calendar_html(int(year), month, events), unsafe_allow_html=True)
    for e in events:
        with st.expander(f'{e["event_date"]} · {", ".join(e["tickers"])} · {e["title"]}'):
            st.write(f'{MILESTONES[e["milestone"]]} · {STATUSES[e["status"]]}')
            st.caption("Nguồn: " + ("Tên miền chính thức" if e["official_source"] else "Chưa xác minh nguồn chính thức"))
            st.write(e["evidence"])
            if safe_url(e["source_url"]):
                source_link("Xem thông báo / bài nguồn", e["source_url"])
    if not events:
        st.info("Chưa có sự kiện có ngày xác định trong tháng này. Bạn có thể thêm mốc đã đối chiếu ở bên dưới.")
    x, y = st.columns(2)
    x.download_button("Xuất lịch tháng (.ics)", events_ics(events), "stock-news-calendar.ics", "text/calendar", disabled=not events)
    y.download_button("Xuất sự kiện CSV", events_csv(events), "stock-news-events.csv", "text/csv", disabled=not events)
    st.caption("File .ics dùng để nhập vào Google Calendar, Apple Calendar hoặc Outlook; không tự đồng bộ khi ngày thay đổi.")
    with st.expander(f"Cần đối chiếu ngày ({len(review)})"):
        for e in review[:50]:
            st.write(e["title"])
            st.caption(e["review_reason"])
            if e["raw_date"]:
                st.write("Mốc đọc được: " + e["raw_date"])
            if safe_url(e["source_url"]):
                source_link("Mở nguồn để kiểm tra", e["source_url"])
    changed = False
    with st.expander("Thêm / sửa sự kiện của bạn"):
        options = {"new": "Thêm mới", **{e["id"]: f'{e["event_date"]} · {e["title"]}' for e in profile["manual_events"]}}
        selected = st.selectbox("Sự kiện cần sửa", list(options), format_func=options.get, key="manual_event_selected")
        old = next((e for e in profile["manual_events"] if e["id"] == selected), {})
        with st.form("manual_event_"+selected):
            title = st.text_input("Tên sự kiện", value=old.get("title", ""), max_chars=500)
            symbols = st.text_input("Mã liên quan", value=", ".join(old.get("tickers", [])))
            when = st.date_input("Ngày diễn ra", value=date.fromisoformat(old["event_date"]) if old else today,
                                 min_value=date(2000,1,1), max_value=date(2199,12,31))
            kind = st.selectbox("Nhóm sự kiện", list(EVENT_TYPES), index=list(EVENT_TYPES).index(old.get("type","other")), format_func=EVENT_TYPES.get)
            statuses = [x for x in STATUSES if x != "needs_review"]
            status = st.selectbox("Trạng thái", statuses, index=statuses.index(old.get("status","expected")), format_func=STATUSES.get)
            source = st.text_input("Link thông báo / nguồn đối chiếu", value=old.get("source_url", ""))
            note = st.text_area("Ghi chú / trích dẫn nguồn", value=old.get("evidence", ""))
            save = st.form_submit_button("Lưu sự kiện", disabled=not st.session_state.get("profile_ready", False))
        if save:
            try:
                if len(profile["manual_events"]) >= 200 and not old:
                    raise ValueError("Tối đa 200 sự kiện đã lưu.")
                event = validate_manual_event({"id": old.get("id"), "event_date": when.isoformat(), "title": title,
                                               "tickers": symbols, "type": kind, "status": status,
                                               "source_url": source, "evidence": note})
                profile["manual_events"] = [e for e in profile["manual_events"] if e["id"] != event["id"]] + [event]
                changed = True
                st.success("Đã lưu. Lịch sẽ cập nhật khi bạn chuyển tháng hoặc mở lại tab.")
            except ValueError as exc:
                st.error(str(exc))
        if old and st.button("Xóa sự kiện tự nhập này"):
            profile["manual_events"] = [e for e in profile["manual_events"] if e["id"] != selected]
            changed = True
    return changed
