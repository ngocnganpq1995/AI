"""Reference daily prices, strict CSV import and news/session alignment."""
from io import BytesIO
import re
import numpy as np
import pandas as pd
import requests


class PriceUnavailable(ValueError):
    pass


PRICE_PERIODS = {"1mo": (1, 35), "3mo": (3, 100), "6mo": (6, 200), "1y": (12, 380)}


def validate_prices(frame):
    if not {"date", "close", "volume"}.issubset(frame.columns):
        raise PriceUnavailable("CSV cần các cột date, close, volume.")
    frame = frame[["date", "close", "volume"]].copy()
    if not 2 <= len(frame) <= 10000:
        raise PriceUnavailable("Cần từ 2 đến 10.000 dòng giá.")
    if not pd.api.types.is_datetime64_any_dtype(frame["date"]):
        if not frame["date"].astype(str).str.fullmatch(r"\d{4}-\d{2}-\d{2}").all():
            raise PriceUnavailable("Ngày CSV cần định dạng YYYY-MM-DD để tránh nhầm ngày/tháng.")
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce").dt.normalize()
    for field in ("close", "volume"):
        frame[field] = pd.to_numeric(frame[field], errors="coerce")
    if frame.isna().any().any() or not np.isfinite(frame[["close", "volume"]].to_numpy()).all():
        raise PriceUnavailable("Ngày hoặc số không hợp lệ. Dùng ngày YYYY-MM-DD, số không có dấu phân cách hàng nghìn.")
    if frame["date"].duplicated().any() or (frame.close <= 0).any() or (frame.volume < 0).any():
        raise PriceUnavailable("Ngày không được trùng; giá phải dương và khối lượng không âm.")
    return frame.sort_values("date").reset_index(drop=True)


def import_prices(data):
    if len(data) > 2_000_000:
        raise PriceUnavailable("CSV tối đa 2 MB.")
    try:
        frame = pd.read_csv(BytesIO(data), encoding="utf-8-sig", sep=None, engine="python")
        return validate_prices(frame)
    except (ValueError, UnicodeError, pd.errors.ParserError) as exc:
        raise PriceUnavailable(str(exc)) from exc


def _price_meta(source, ticker, adjustment):
    return {"source": source, "symbol": ticker, "currency": "VND",
            "fetched": pd.Timestamp.now(tz="Asia/Ho_Chi_Minh").strftime("%d/%m/%Y %H:%M"),
            "adjustment": adjustment}


def _fetch_yahoo_prices(ticker, period):
    try:
        response = requests.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}.VN",
                                params={"range": period, "interval": "1d"},
                                headers={"User-Agent": "Mozilla/5.0"}, timeout=(5,15))
        response.raise_for_status()
        result = response.json()["chart"]["result"][0]
        if result["meta"].get("currency") != "VND":
            raise PriceUnavailable("Nguồn giá không trả đơn vị VND cho mã này.")
        quote = result["indicators"]["quote"][0]
        frame = pd.DataFrame({"date": pd.to_datetime(result["timestamp"], unit="s", utc=True).tz_convert("Asia/Ho_Chi_Minh").tz_localize(None).normalize(),
                              "close": quote["close"], "volume": quote["volume"]}).dropna()
        frame = validate_prices(frame)
        return frame, _price_meta("Yahoo Finance", ticker+".VN",
                                  "Giá close do nguồn cung cấp; không dùng adjusted close. Chưa xác minh điều chỉnh chia tách.")
    except (requests.RequestException, ValueError, KeyError, TypeError, IndexError) as exc:
        raise PriceUnavailable("Yahoo Finance chưa cung cấp lịch sử giá mã này.") from exc


def _fetch_simplize_prices(ticker, period):
    months, _ = PRICE_PERIODS[period]
    try:
        response = requests.get(
            "https://api2.simplize.vn/api/historical/prices/ohlcv",
            params={"ticker": ticker}, headers={"User-Agent": "Mozilla/5.0",
                                                 "Origin": "https://simplize.vn"}, timeout=(5, 15))
        response.raise_for_status()
        payload = response.json()
        data = payload.get("data")
        if payload.get("status") != 200 or not isinstance(data, list) or len(data) > 10000:
            raise ValueError("Phản hồi giá không hợp lệ")
        if any(not isinstance(row, list) or len(row) != 6 for row in data):
            raise ValueError("Cột giá không hợp lệ")
        frame = pd.DataFrame(data, columns=["timestamp", "open", "high", "low", "close", "volume"])
        frame["date"] = pd.to_datetime(pd.to_numeric(frame["timestamp"], errors="raise"),
                                       unit="s", utc=True).dt.tz_convert("Asia/Ho_Chi_Minh").dt.tz_localize(None).dt.normalize()
        cutoff = (pd.Timestamp.now(tz="Asia/Ho_Chi_Minh").tz_localize(None).normalize()
                  - pd.DateOffset(months=months))
        frame = validate_prices(frame.loc[frame["date"] >= cutoff, ["date", "close", "volume"]])
        return frame, _price_meta("Simplize", ticker,
                                  "Giá OHLCV do Simplize cung cấp; chưa xác minh điều chỉnh chia tách hoặc cổ tức.")
    except (requests.RequestException, ValueError, KeyError, TypeError, IndexError) as exc:
        raise PriceUnavailable("Simplize chưa cung cấp lịch sử giá mã này.") from exc


def _fetch_vietcap_prices(ticker, period):
    months, count_back = PRICE_PERIODS[period]
    try:
        response = requests.post(
            "https://trading.vietcap.com.vn/api/chart/OHLCChart/gap-chart",
            json={"timeFrame": "ONE_DAY", "symbols": [ticker],
                  "to": int(pd.Timestamp.now(tz="UTC").timestamp()), "countBack": count_back},
            headers={"User-Agent": "Mozilla/5.0", "Origin": "https://trading.vietcap.com.vn",
                     "Referer": "https://trading.vietcap.com.vn/"}, timeout=(5, 15))
        response.raise_for_status()
        result = response.json()
        if not isinstance(result, list) or len(result) != 1 or result[0].get("symbol") != ticker:
            raise ValueError("Mã từ nguồn giá không khớp")
        quote = result[0]
        if not (len(quote["t"]) == len(quote["c"]) == len(quote["v"])):
            raise ValueError("Các cột giá không khớp")
        frame = pd.DataFrame({
            "date": pd.to_datetime(pd.to_numeric(quote["t"], errors="raise"), unit="s", utc=True).tz_convert("Asia/Ho_Chi_Minh").tz_localize(None).normalize(),
            "close": quote["c"], "volume": quote["v"],
        }).dropna()
        cutoff = (pd.Timestamp.now(tz="Asia/Ho_Chi_Minh").tz_localize(None).normalize()
                  - pd.DateOffset(months=months))
        frame = validate_prices(frame.loc[frame["date"] >= cutoff])
        return frame, _price_meta("Vietcap", ticker,
                                  "Giá đóng cửa do Vietcap cung cấp; chưa xác minh điều chỉnh chia tách hoặc cổ tức.")
    except (requests.RequestException, ValueError, KeyError, TypeError, IndexError) as exc:
        raise PriceUnavailable("Vietcap chưa cung cấp lịch sử giá mã này.") from exc


def fetch_prices(ticker, period="3mo"):
    if not re.fullmatch(r"[A-Z0-9]{2,10}", ticker) or period not in PRICE_PERIODS:
        raise PriceUnavailable("Mã hoặc khoảng giá không hợp lệ.")
    try:
        return _fetch_yahoo_prices(ticker, period)
    except PriceUnavailable:
        try:
            return _fetch_simplize_prices(ticker, period)
        except PriceUnavailable:
            try:
                return _fetch_vietcap_prices(ticker, period)
            except PriceUnavailable as exc:
                raise PriceUnavailable("Chưa lấy được lịch sử giá từ Yahoo Finance, Simplize hoặc Vietcap.") from exc


def align_news(prices, articles, ticker):
    rows = []
    for item in articles:
        if ticker not in item.get("tickers", [item.get("ticker")]):
            continue
        stamp = pd.to_datetime(item.get("published_dt"), utc=True, errors="coerce")
        if pd.isna(stamp):
            continue
        day = stamp.tz_convert("Asia/Ho_Chi_Minh").tz_localize(None).normalize()
        if day < prices.date.min() or day > prices.date.max():
            continue
        # Daily chart: same day if traded, otherwise next observed session.
        following = prices.loc[(prices.date >= day) & (prices.volume > 0)]
        if following.empty:
            continue
        bar = following.iloc[0]
        rows.append({"date": bar.date, "published_date": day.strftime("%Y-%m-%d"), "close": bar.close,
                     "title": item["title"], "source": item.get("source", ""), "url": item.get("url", "")})
    return pd.DataFrame(rows, columns=["date", "published_date", "close", "title", "source", "url"])
