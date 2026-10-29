import altair as alt
import streamlit as st
from market_prices import fetch_prices, import_prices, align_news, PriceUnavailable


@st.cache_data(ttl=1800, show_spinner=False)
def cached_prices(ticker, period):
    return fetch_prices(ticker, period)


def render_price_timeline(articles, watched_tickers):
    st.markdown("### Giá đi cùng câu chuyện.")
    st.caption("Giá và khối lượng theo ngày, kèm dấu mốc bài báo. Đây là đối chiếu thời gian, không khẳng định tin gây ra biến động giá.")
    a, b = st.columns(2)
    ticker = a.selectbox("Mã xem biểu đồ", sorted(set(watched_tickers) or {"FPT"}), key="price_ticker")
    period = b.selectbox("Khoảng lịch sử", ["1mo","3mo","6mo","1y"], index=1,
                         format_func={"1mo":"1 tháng","3mo":"3 tháng","6mo":"6 tháng","1y":"1 năm"}.get)
    mode = st.radio("Nguồn dữ liệu giá", ["Giá tham khảo Yahoo Finance", "CSV của tôi"], horizontal=True)
    selected_key = (ticker, period, mode)
    if mode == "Giá tham khảo Yahoo Finance":
        if st.button("Tải biểu đồ giá", type="primary"):
            try:
                with st.spinner("Đang tải lịch sử giá…"):
                    frame, meta = cached_prices(ticker, period)
                st.session_state.price_result = (selected_key, frame, meta)
            except PriceUnavailable as exc:
                st.error(str(exc))
        st.caption("Nguồn bên ngoài có thể trễ hoặc thiếu mã. Biểu đồ không dùng để đặt lệnh. Giá và khối lượng hiển thị theo dữ liệu nhà cung cấp.")
    else:
        st.caption("CSV UTF-8 gồm date (YYYY-MM-DD), close (VND/cổ phiếu), volume (cổ phiếu). Giá dùng dấu chấm thập phân, không có dấu phân cách hàng nghìn.")
        st.download_button("Tải mẫu cột CSV", "date,close,volume\n", "price-template.csv", "text/csv")
        upload = st.file_uploader("Lịch sử giá của mã đang chọn", type=["csv"], key="price_csv")
        adjusted = st.selectbox("Trạng thái điều chỉnh của CSV", ["Chưa xác định", "Giá chưa điều chỉnh", "Giá đã điều chỉnh"])
        if st.button("Dùng dữ liệu CSV", disabled=upload is None):
            try:
                frame = import_prices(upload.getvalue())
                st.session_state.price_result = (selected_key, frame, {"source":"CSV của bạn", "symbol":ticker,
                                                   "fetched":"Do bạn cung cấp", "adjustment":adjusted})
            except PriceUnavailable as exc:
                st.error(str(exc))
    result = st.session_state.get("price_result")
    if not result or result[0] != selected_key:
        st.info("Chọn mã và tải dữ liệu để xem biểu đồ cùng tin đã quét.")
        return
    _, frame, meta = result
    st.caption(f'{meta["source"]} · {meta["symbol"]} · VND/cổ phiếu · Tải lúc {meta["fetched"]} (UTC+7) · Phiên cuối: {frame.date.max():%d/%m/%Y}')
    st.caption(meta["adjustment"])
    st.caption("Giá của phiên đang diễn ra có thể còn thay đổi. Các điểm tin chỉ gắn vào ngày có khối lượng giao dịch lớn hơn 0.")
    points = align_news(frame, articles, ticker)
    chart = alt.Chart(frame).mark_line(color="#88465f").encode(
        x=alt.X("date:T", title="Ngày giao dịch"), y=alt.Y("close:Q", title="Giá đóng cửa (VND)", scale=alt.Scale(zero=False)),
        tooltip=[alt.Tooltip("date:T", title="Phiên"), alt.Tooltip("close:Q", title="Giá", format=",.0f")])
    if not points.empty:
        markers = alt.Chart(points).mark_point(size=100, filled=True, color="#88465f", shape="diamond").encode(
            x="date:T", y="close:Q", tooltip=["title:N", "source:N", "published_date:N", "date:T"])
        chart = chart + markers
    st.altair_chart(chart.properties(height=330).interactive(), width="stretch")
    volume = alt.Chart(frame).mark_bar(color="#e4a4bd").encode(x=alt.X("date:T", title=None),
                       y=alt.Y("volume:Q", title="Khối lượng (cổ phiếu)"), tooltip=["date:T","volume:Q"])
    st.altair_chart(volume.properties(height=120), width="stretch")
    st.caption("Tin trong ngày đặt tại phiên cùng ngày, kể cả tin sau giờ đóng cửa. Tin ngày nghỉ đặt ở phiên tiếp theo có dữ liệu; không đặt điểm vào phiên tương lai chưa có giá.")
    if points.empty:
        st.info("Chưa có tin của mã này trong khoảng giá. Quét thêm tin ở tab Stock News.")
    else:
        from investor_events import safe_url
        for _, row in points.iterrows():
            st.write(f'{row.published_date} · {row.title}')
            if safe_url(row.url):
                st.link_button("Xem bài nguồn", row.url)
    st.download_button("Tải dữ liệu giá đang xem", frame.to_csv(index=False).encode("utf-8-sig"), f"{ticker}-prices.csv", "text/csv")
