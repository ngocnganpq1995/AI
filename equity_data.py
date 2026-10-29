"""Public Simplize snapshots; no synthetic financial data or inferred dates."""
import json
import math
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import requests
from bs4 import BeautifulSoup

API = "https://api.simplize.vn"


class EquityUnavailable(ValueError):
    pass


def valid_ticker(ticker):
    ticker = str(ticker).strip().upper()
    if not re.fullmatch(r"[A-Z][A-Z0-9]{1,9}", ticker):
        raise EquityUnavailable("Mã cổ phiếu không hợp lệ.")
    return ticker


def public_data(path, params=None):
    try:
        response = requests.get(API+path, params=params, headers={"User-Agent":"Mozilla/5.0"}, timeout=(5,15))
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict) or payload.get("status") != 200 or not isinstance(payload.get("data"), list):
            raise ValueError("Dữ liệu không hợp lệ")
        return payload["data"]
    except (requests.RequestException, ValueError) as exc:
        raise EquityUnavailable("Chưa tải được dữ liệu bổ sung từ Simplize.") from exc


def fetch_company(ticker):
    ticker = valid_ticker(ticker)
    url = f"https://simplize.vn/co-phieu/{ticker}"
    try:
        response = requests.get(url, headers={"User-Agent":"Mozilla/5.0"}, timeout=(5,20))
        response.raise_for_status()
        node = BeautifulSoup(response.text, "html.parser").find("script", id="__NEXT_DATA__")
        data = json.loads(node.string)["props"]["pageProps"]
        if data.get("summary", {}).get("ticker") != ticker:
            raise ValueError("Mã không khớp")
    except (requests.RequestException, ValueError, TypeError, KeyError, AttributeError) as exc:
        raise EquityUnavailable(f"Chưa tải được hồ sơ {ticker} từ Simplize.") from exc
    data["ticker"] = ticker
    data["source_url"] = url
    data["fetched"] = datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).isoformat(timespec="seconds")
    from financial_fallback import supplement
    return supplement(data)


def fetch_ownership(ticker):
    ticker = valid_ticker(ticker)
    url = "https://cafef.vn/du-lieu/Ajax/CongTy/BanLanhDao.aspx"
    try:
        response = requests.get(url, params={"sym":ticker}, timeout=(5,20))
        response.raise_for_status()
        return parse_cafef_ownership(response.text, ticker)
    except requests.RequestException as exc:
        raise EquityUnavailable(f"Chưa tải được cơ cấu cổ đông {ticker} từ CafeF.") from exc


def fetch_ownership_structure(ticker):
    ticker = valid_ticker(ticker)
    url = 'https://cafef.vn/du-lieu/Ajax/PageNew/CoCauSoHuu.ashx'
    try:
        response = requests.get(url, params={'Symbol':ticker}, timeout=(5,20))
        response.raise_for_status()
        payload = response.json()
        if not payload.get('Success') or not isinstance(payload.get('Data'),dict):
            raise ValueError('Missing ownership')
        return parse_ownership_structure(payload['Data'], ticker)
    except (requests.RequestException, ValueError, TypeError, AttributeError) as exc:
        raise EquityUnavailable(f'Chưa tải được biểu đồ sở hữu {ticker} từ CafeF.') from exc


def parse_ownership_structure(data, ticker):
    rows=[]
    for r in data.get('CoDongSoHuu') or []:
        pct=number(str(r.get('AssetRate','')).replace(',','.'))
        shares=number(str(r.get('AssetVolume','')).replace('.','').replace(',',''))
        if pct is not None and 0 <= pct <= 100:
            rows.append({'Cổ đông':text_only(r.get('Name')), 'Tỷ lệ (%)':pct,
                         'Số cổ phiếu':int(shares) if shares is not None else None,
                         'Tính đến ngày':r.get('UpdatedDate',''),
                         'Nguồn':f'https://cafef.vn/du-lieu/Ajax/PageNew/CoCauSoHuu.ashx?Symbol={ticker}'})
    groups=[]
    for key,label in [('NuocNgoai','Sở hữu nước ngoài'),('NhaNuoc','Sở hữu nhà nước'),('Khac','Sở hữu khác')]:
        pct=number(data.get(key))
        if pct is not None and 0 <= pct <= 100:
            groups.append({'Nhóm':label,'Tỷ lệ (%)':pct})
    if not rows and not groups:
        raise ValueError('No shareholders')
    if len(groups)!=3 or abs(sum(r['Tỷ lệ (%)'] for r in groups)-100)>.1:
        groups=[]
    return {'rows':sorted(rows, key=lambda row: row['Tỷ lệ (%)'], reverse=True),'groups':groups}


def parse_cafef_ownership(markup, ticker):
    """Read the shareholder table, not the board-members table or foreign room."""
    soup = BeautifulSoup(markup, "html.parser")
    rows = []
    for tr in soup.select("tr"):
        cells = tr.find_all("td", recursive=False)
        if len(cells) != 4:
            continue
        values = [c.get_text(" ",strip=True) for c in cells]
        if not re.fullmatch(r"\d{2}/\d{2}/\d{4}",values[3]):
            continue
        pct = number(values[2].replace(",","."))
        shares = number(values[1].replace(".","").replace(",",""))
        if pct is not None and 0 <= pct <= 100 and shares is not None and values[0]:
            rows.append({"Cổ đông":values[0],"Tỷ lệ (%)":pct,"Số cổ phiếu":int(shares),
                         "Tính đến ngày":values[3],"Nguồn":f"https://cafef.vn/du-lieu/Ajax/CongTy/BanLanhDao.aspx?sym={ticker}"})
    if not rows:
        raise EquityUnavailable(f"CafeF chưa có bảng cổ đông đọc được cho {ticker}.")
    return rows


def ownership_chart_rows(rows):
    """CafeF outer ring: holdings >=1%, plus remainder only below 100%."""
    selected = [r for r in rows if r['Tỷ lệ (%)'] >= 1]
    if not selected:
        return []
    result = [{"Cổ đông":r["Cổ đông"],"Tỷ lệ (%)":r["Tỷ lệ (%)"]}
              for r in sorted(selected,key=lambda r:r["Tỷ lệ (%)"],reverse=True)]
    remaining = round(100-sum(r["Tỷ lệ (%)"] for r in result),2)
    if remaining > 0:
        result.append({"Cổ đông":"Khác / phần còn lại","Tỷ lệ (%)":remaining})
    return result


def fetch_events(ticker):
    return public_data("/api/company/events/list", {"ticker":valid_ticker(ticker),"isWl":"false","page":0,"size":100})


def number(value):
    try:
        n = float(value)
        return n if math.isfinite(n) else None
    except (ValueError, TypeError):
        return None


def source_date(value):
    if value is None or value == "":
        return ""
    try:
        if re.fullmatch(r"\d{2}/\d{2}/\d{4}", str(value)):
            return datetime.strptime(value, "%d/%m/%Y").date().isoformat()
        stamp = pd.to_datetime(value, unit="ms", utc=True) if isinstance(value, (int, float)) or str(value).isdigit() else pd.to_datetime(value, utc=True)
        return stamp.tz_convert("Asia/Ho_Chi_Minh").strftime("%Y-%m-%d") if not pd.isna(stamp) else ""
    except (ValueError, TypeError, OverflowError):
        return ""


def text_only(value):
    return BeautifulSoup(str(value or ""), "html.parser").get_text(" ", strip=True)


def company_events(company):
    """Explicit corporate dates, with publication dates labeled separately."""
    from investor_events import safe_url
    rows = []
    ticker, url = company["ticker"], company["source_url"]
    def append(when, title, kind, label, link):
        day = source_date(when)
        if day:
            rows.append({"Ngày":day,"Mã":ticker,"Sự kiện":text_only(title),"Nhóm":kind,
                         "Loại ngày":label,"Nguồn":safe_url(link) or url})
    explicit_days = {source_date(x.get("exDividendDate")) for x in company.get("events", [])}
    for item in company.get("dividendPayment", []):
        if source_date(item.get("date")) in explicit_days:
            continue
        title = text_only(item.get("content"))
        kind = "Cổ tức" if "cổ tức" in title.lower() else "Phát hành / thưởng cổ phiếu"
        append(item.get("date"), title, kind, "Ngày lịch sử theo nguồn (chưa xác định loại ngày)", url)
    for item in company.get("events", []) + company.get("companyNews", []):
        title = text_only(item.get("description") or item.get("title"))
        low = title.lower()
        kind = ("Phát hành / thưởng cổ phiếu" if any(x in low for x in ("phát hành", "tăng vốn", "esop", "thưởng cổ phiếu")) else
                "Cổ tức" if "cổ tức" in low else "Đại hội cổ đông" if any(x in low for x in ("đại hội", "đhđcđ", "đhcđ")) else "Công bố doanh nghiệp")
        found = False
        for key, label in [("exDividendDate","Giao dịch không hưởng quyền"),("recordDate","Đăng ký cuối cùng"),("executionDate","Ngày thực hiện")]:
            if source_date(item.get(key)):
                append(item[key],title,kind,label,item.get("attachedLink")); found = True
        if not found:
            append(item.get("createdDate"), title, kind, "Ngày công bố (không phải ngày thực hiện)", item.get("attachedLink"))
    unique = {(r["Ngày"],r["Sự kiện"],r["Loại ngày"]):r for r in rows}
    return sorted(unique.values(), key=lambda x:x["Ngày"], reverse=True)


def valuation_row(company):
    s = company["summary"]
    cap = number(s.get("marketCap"))
    return {"Mã":company["ticker"], "Doanh nghiệp":s.get("name", ""), "Ngành":s.get("industryActivity", ""),
            "Giá tham chiếu nguồn (đ/CP)":number(s.get("priceClose")), "P/E (TTM)":number(s.get("peRatio")),
            "P/B (FQ)":number(s.get("pbRatio")), "Vốn hóa (tỷ đồng)":cap/1e9 if cap is not None else None,
            "EPS (TTM, đ/CP)":number(s.get("epsRatio")), "BVPS (đ/CP)":number(s.get("bookValue")),
            "ROE (%)":number(s.get("roe")), "Nguồn cập nhật":s.get("analysisUpdated", "Chưa rõ"),
            "Nguồn":company["source_url"],
            "Kỳ số liệu bổ sung":'; '.join(f'{dict(epsRatio="EPS",bookValue="BVPS",roe="ROE")[k]}: {v}' for k,v in company.get('metric_notes',{}).items()),
            "Nguồn bổ sung":f'https://cafef.vn/du-lieu/Ajax/PageNew/ChiSoTaiChinh.ashx?Symbol={company["ticker"]}' if company.get('metric_notes') else '',
            "Chỉ số bổ sung":', '.join(company.get('metric_notes',{}))}


def industry_candidates(company):
    s = company['summary']
    sector, industry = s.get('bcEconomicSectorSlug'), s.get('bcIndustryGroupSlug')
    if not sector or not industry:
        return company.get('stocks', [])
    try:
        url = f'https://simplize.vn/co-phieu/nganh/{sector}/{industry}'
        response = requests.get(url, timeout=(5,20))
        response.raise_for_status()
        node = BeautifulSoup(response.text, 'html.parser').find('script', id='__NEXT_DATA__')
        page = json.loads(node.string)['props']['pageProps']
        if page.get('subSlug') != industry:
            raise ValueError('Wrong industry')
        return [r for r in page['dataFilter'] if r.get('industrySlug') == industry]
    except (requests.RequestException, ValueError, KeyError, TypeError, AttributeError) as exc:
        raise EquityUnavailable('Chưa tải được danh sách ngành; đang dùng các mã gợi ý của nguồn.') from exc


def comparable_rows(company, fetcher=fetch_company, candidate_fetcher=industry_candidates):
    """Verify industry for each suggested peer; never assume related means same industry."""
    base = valuation_row(company)
    rows, errors = [base], []
    try:
        candidates = candidate_fetcher(company)
    except EquityUnavailable as exc:
        errors.append(str(exc))
        candidates = company.get('stocks', [])
    candidates = sorted(candidates, key=lambda r:number(r.get('marketCapVnd')) or 0, reverse=True)
    candidates = list(dict.fromkeys(x.get('ticker') for x in candidates if x.get('ticker') and x['ticker'] != company['ticker']))[:15]
    def get(code):
        try:
            return fetcher(code)
        except EquityUnavailable:
            return None
    with ThreadPoolExecutor(max_workers=4) as pool:
        for code, other in zip(candidates, pool.map(get, candidates)):
            if other is None:
                errors.append(code)
            elif company['summary'].get('bcIndustryGroupId') is not None and other['summary'].get('bcIndustryGroupId') == company['summary']['bcIndustryGroupId']:
                rows.append(valuation_row(other))
    return rows[:1] + sorted(rows[1:], key=lambda r:r.get('Vốn hóa (tỷ đồng)') or 0, reverse=True)[:10], errors


def relative_valuation(rows):
    """Positive peer multiples only; target excluded from median. No target price for losses."""
    result = []
    if not rows:
        return result
    target = rows[0]
    for multiple, base in [("P/E (TTM)","EPS (TTM, đ/CP)"),("P/B (FQ)","BVPS (đ/CP)")]:
        if ('epsRatio' if multiple == 'P/E (TTM)' else 'bookValue') in target.get('Chỉ số bổ sung', ''):
            continue  # Historical fallback must not be paired with current peer multiples.
        peers = [r[multiple] for r in rows[1:] if number(r.get(multiple)) is not None and r[multiple] > 0]
        amount = number(target.get(base))
        if len(peers) >= 2 and amount is not None and amount > 0:
            median = float(pd.Series(peers).median())
            result.append({"Phương pháp":multiple,"Số mã đối chiếu":len(peers),"Trung vị nhóm":median,
                           "Giá tham chiếu tương đối (đ/CP)":median*amount})
    return result
