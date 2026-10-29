"""Browser-private investor workspace with validated, portable JSON backups."""
from datetime import datetime
import hashlib
import json
import re
import uuid

import streamlit as st
from streamlit.components.v2 import component
from investor_events import validate_manual_event


def default_profile():
    return {"version": 1, "groups": {"Đang theo dõi": ["FPT", "TCB", "VIC", "VHM", "PVS"]},
            "read": [], "seen": [], "saved": {}, "manual_events": [], "recent_news": []}


def parse_tickers(text):
    values = re.split(r"[,;\s]+", str(text).strip().upper())
    return list(dict.fromkeys(t for t in values if re.fullmatch(r"[A-Z0-9]{2,10}", t)))[:30]


def article_id(article):
    return hashlib.sha256(str(article.get("url") or article.get("title", "")).encode()).hexdigest()[:24]


def portable_article(item):
    clean = {k: str(item.get(k, ""))[:16000] for k in
             ("title", "url", "source", "date", "published", "summary", "article_text", "bond_info")}
    raw_tickers = item.get("tickers", [])
    clean["tickers"] = parse_tickers(raw_tickers if isinstance(raw_tickers,str) else ",".join(map(str, raw_tickers)))
    stamp = item.get("published_dt")
    clean["published_dt"] = stamp.isoformat() if isinstance(stamp,datetime) else str(stamp or "")
    return clean


def validate_profile(value):
    if not isinstance(value, dict) or value.get("version") != 1:
        raise ValueError("Bản sao lưu không đúng định dạng Stock News v1.")
    out = default_profile()
    groups = value.get("groups", {})
    if not isinstance(groups, dict) or len(groups) > 20:
        raise ValueError("Tối đa 20 danh sách theo dõi.")
    out["groups"] = {str(k).strip()[:60]: parse_tickers(",".join(map(str, v)))
                     for k, v in groups.items() if str(k).strip() and isinstance(v, list)} or out["groups"]
    for key in ("read", "seen"):
        ids = value.get(key, [])
        if not isinstance(ids, list):
            raise ValueError("Danh sách trạng thái tin không hợp lệ.")
        out[key] = list(dict.fromkeys(str(x) for x in ids if re.fullmatch(r"[a-f0-9]{24}", str(x))))[-5000:]
    saved = value.get("saved", {})
    if not isinstance(saved, dict) or len(saved) > 100:
        raise ValueError("Tối đa 100 tin đã lưu.")
    out["saved"] = {}
    for key, item in saved.items():
        if not isinstance(item, dict):
            continue
        clean = portable_article(item)
        out["saved"][article_id(clean)] = clean
    recent = value.get("recent_news", [])
    if not isinstance(recent, list) or len(recent) > 60:
        raise ValueError("Bản lưu giữ tối đa 60 bài gần nhất.")
    out["recent_news"] = [portable_article(item) for item in recent if isinstance(item,dict)]
    events = value.get("manual_events", [])
    if not isinstance(events, list) or len(events) > 200:
        raise ValueError("Tối đa 200 sự kiện tự lưu.")
    out["manual_events"] = [validate_manual_event(e) for e in events if isinstance(e, dict)]
    return out


def _storage_component():
    return component("stock_news_private_workspace", html='<span role="status" id="storage-status"></span>', js=r'''
export default function({data, parentElement, setStateValue}) {
  const el = parentElement.querySelector('#storage-status');
  const key = 'stock-news-kngan:workspace:v1';
  try {
    if (data.write) {
      localStorage.setItem(key, JSON.stringify(data.profile));
      el.textContent = 'Đã lưu trên trình duyệt này';
      setStateValue('saved', data.revision);
    } else {
      const raw = localStorage.getItem(key);
      setStateValue('loaded', {nonce:data.nonce, profile:raw ? JSON.parse(raw) : null});
      el.textContent = 'Không gian riêng · Lưu trên trình duyệt này';
    }
  } catch (e) {
    el.textContent = 'Trình duyệt chưa cho lưu. Bạn có thể tải bản sao lưu JSON.';
    setStateValue('storage_error', true);
    setStateValue('loaded', {nonce:data.nonce, profile:null});
  }
}
''', css='span {color:#786b70;font:12px sans-serif;line-height:1.6}')


def get_profile():
    if "investor_profile" not in st.session_state:
        st.session_state.investor_profile = default_profile()
    st.session_state.setdefault("profile_revision", 0)
    st.session_state.setdefault("profile_ready", False)
    st.session_state.setdefault("profile_nonce", str(uuid.uuid4()))
    st.session_state.setdefault("previous_seen", set())
    return st.session_state.investor_profile


def changed():
    st.session_state.profile_revision += 1


def persist_profile():
    profile = get_profile()
    result = _storage_component()(data={"write": st.session_state.profile_ready,
                            "profile": profile if st.session_state.profile_ready else None,
                            "revision": st.session_state.profile_revision,
                            "nonce": st.session_state.profile_nonce}, key="private_workspace",
                      on_loaded_change=lambda: None, on_saved_change=lambda: None,
                      on_storage_error_change=lambda: None)
    loaded = result.loaded
    if not st.session_state.profile_ready and loaded:
        try:
            if loaded.get("profile") is not None:
                st.session_state.investor_profile = validate_profile(loaded["profile"])
                if not st.session_state.get("merged_news"):
                    restored = []
                    for item in st.session_state.investor_profile["recent_news"]:
                        item = dict(item)
                        try:
                            item["published_dt"] = datetime.fromisoformat(item["published_dt"])
                        except ValueError:
                            item["published_dt"] = None
                        item["tickers"] = set(item["tickers"])
                        restored.append(item)
                    st.session_state.merged_news = restored
        except (ValueError, TypeError):
            st.warning("Bản lưu cũ không đọc được. Bạn có thể nhập bản sao lưu trong mục Danh sách & tin lưu.")
        st.session_state.previous_seen = set(st.session_state.investor_profile["seen"])
        st.session_state.profile_ready = True
        st.rerun()


def watchlist_selector(profile):
    names = list(profile["groups"])
    if st.session_state.get("watch_group") not in names:
        st.session_state.watch_group = names[0]
    group = st.selectbox("Danh sách đã lưu", names, key="watch_group")
    if st.button("Dùng danh sách này", key="apply_watchlist", disabled=not st.session_state.profile_ready):
        st.session_state.news_tickers = ", ".join(profile["groups"][group])


def mark_seen(articles, profile):
    profile["seen"] = list(dict.fromkeys(profile["seen"] + [article_id(a) for a in articles]))[-5000:]
    profile["recent_news"] = [portable_article(a) for a in articles[:60]]
    changed()


def article_controls(item, profile):
    ident = article_id(item)
    is_read, is_saved = ident in profile["read"], ident in profile["saved"]
    c1, c2, c3 = st.columns([1, 1, 2])
    if c1.button("Đánh dấu chưa đọc" if is_read else "Đánh dấu đã đọc", key="read_"+ident,
                 disabled=not st.session_state.profile_ready):
        profile["read"] = [x for x in profile["read"] if x != ident] if is_read else (profile["read"] + [ident])[-5000:]
        changed()
        st.rerun()
    if c2.button("Bỏ lưu tin" if is_saved else "Lưu tin ☆", key="save_"+ident,
                 disabled=not st.session_state.profile_ready):
        if is_saved:
            profile["saved"].pop(ident)
        elif len(profile["saved"]) >= 100:
            st.warning("Bạn đã lưu 100 tin. Hãy bỏ lưu một tin trước khi thêm.")
            return
        else:
            saved = {k: item.get(k, "") for k in ("title", "url", "source", "date", "published", "summary", "article_text")}
            saved["tickers"] = sorted(item.get("tickers", []))
            profile["saved"][ident] = saved
        changed()
        st.rerun()
    c3.caption(("Đã đọc" if is_read else "Chưa đọc") + (" · Mới từ lần xem trước" if ident not in st.session_state.previous_seen else ""))


def workspace_view(profile):
    st.markdown("### Góc lưu của bạn.")
    st.caption("Danh sách, trạng thái đọc, tin lưu và lịch tự nhập được lưu trên trình duyệt này. Dùng bản sao lưu để chuyển thiết bị.")
    with st.form("watchlist_form"):
        name = st.text_input("Tên danh sách", placeholder="VD: Đang nắm giữ")
        symbols = st.text_input("Các mã trong danh sách", value=st.session_state.get("news_tickers", "FPT, TCB"))
        save = st.form_submit_button("Lưu danh sách", disabled=not st.session_state.profile_ready)
    if save:
        if not name.strip() or not parse_tickers(symbols):
            st.error("Nhập tên và ít nhất một mã hợp lệ.")
        elif len(profile["groups"]) >= 20 and name.strip() not in profile["groups"]:
            st.error("Tối đa 20 danh sách.")
        else:
            profile["groups"][name.strip()[:60]] = parse_tickers(symbols)
            changed()
            st.rerun()
    st.dataframe([{"Danh sách": k, "Mã cổ phiếu": ", ".join(v)} for k, v in profile["groups"].items()], hide_index=True, width="stretch")
    with st.expander("Quản lý danh sách & bản sao lưu"):
        group = st.selectbox("Danh sách muốn xóa", list(profile["groups"]), key="delete_group")
        if st.button("Xóa danh sách đã chọn", disabled=len(profile["groups"]) < 2 or not st.session_state.profile_ready):
            profile["groups"].pop(group)
            changed()
            st.rerun()
        st.download_button("Tải bản sao lưu JSON", json.dumps(profile, ensure_ascii=False, indent=2),
                           "stock-news-workspace.json", "application/json")
        uploaded = st.file_uploader("Nhập bản sao lưu JSON", type=["json"], key="profile_import")
        if st.button("Khôi phục bản sao lưu", disabled=uploaded is None or not st.session_state.profile_ready):
            try:
                if uploaded.size > 4_000_000:
                    raise ValueError("File quá lớn (tối đa 4 MB).")
                st.session_state.investor_profile = validate_profile(json.loads(uploaded.getvalue()))
                restored = []
                for saved in st.session_state.investor_profile["recent_news"]:
                    item = dict(saved)
                    try:
                        item["published_dt"] = datetime.fromisoformat(item["published_dt"])
                    except (ValueError, TypeError, KeyError):
                        item["published_dt"] = None
                    item["tickers"] = set(item["tickers"])
                    restored.append(item)
                st.session_state.merged_news = restored
                st.session_state.previous_seen = set(st.session_state.investor_profile["seen"])
                changed()
                st.rerun()
            except (ValueError, TypeError, UnicodeError) as exc:
                st.error(str(exc))
    st.markdown("#### Tin đã lưu")
    from investor_events import safe_url
    for ident, item in list(profile["saved"].items()):
        with st.expander(item["title"]):
            st.caption(f'{item["date"]} · {item["source"]} · {", ".join(item["tickers"])}')
            st.write(item["summary"] or item["title"])
            if safe_url(item["url"]):
                st.link_button("Đọc nguồn", item["url"])
            if st.button("Bỏ lưu", key="remove_saved_"+ident):
                profile["saved"].pop(ident)
                changed()
                st.rerun()
    if not profile["saved"]:
        st.info("Nhấn Lưu tin ở phần chi tiết một bài để đọc lại tại đây.")
