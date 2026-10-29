"""Ticker-bound public broker reports, retaining source provenance."""
import html
import math
from datetime import datetime
from zoneinfo import ZoneInfo

import requests

from equity_data import EquityUnavailable, valid_ticker, text_only
from investor_events import safe_url


def parse_reports(data, ticker, latest_only=True):
    ticker = valid_ticker(ticker)
    if data.get('ticker') != ticker:
        raise EquityUnavailable('Mã báo cáo không khớp mã đang tra.')
    rows = []
    for report in data.get('analysisReports') or []:
        if report.get('ticker') != ticker or not report.get('source'):
            continue
        try:
            published = datetime.strptime(report.get('issueDate', ''), '%d/%m/%Y')
        except (ValueError, TypeError):
            continue
        price = report.get('targetPrice')
        if not isinstance(price, (int, float)) or isinstance(price, bool) or not math.isfinite(price) or price <= 0:
            price = None
        rows.append({'broker': text_only(report['source']), 'date': published,
                     'price': price, 'recommend': text_only(report.get('recommend') or ''),
                     'title': text_only(report.get('title') or ''),
                     'url': safe_url(report.get('attachedLink') or '')})
    if not latest_only:
        return sorted(rows, key=lambda r: r['date'], reverse=True)
    return latest_reports(rows)


def latest_reports(rows, year=None):
    latest = {}
    for row in sorted(rows, key=lambda r: r['date'], reverse=True):
        if year is not None and row['date'].year != year:
            continue
        latest.setdefault(row['broker'].casefold(), row)
    return list(latest.values())


def report_years(current_year=None):
    year = current_year if current_year is not None else datetime.now(ZoneInfo('Asia/Bangkok')).year
    return [year, year - 1, year - 2]


def fetch_broker_reports(ticker):
    ticker = valid_ticker(ticker)
    years = report_years()
    rows = []
    try:
        with requests.Session() as session:
            for page in range(20):
                response = session.get('https://api.simplize.vn/api/company/analysis-report/list',
                                       params={'ticker': ticker, 'page': page, 'size': 100, 'isWl': 'false'},
                                       headers={'User-Agent': 'Mozilla/5.0'}, timeout=(5, 20))
                response.raise_for_status()
                payload = response.json()
                if payload.get('status') != 200 or not isinstance(payload.get('data'), list):
                    raise ValueError('Dữ liệu báo cáo không hợp lệ')
                raw = payload['data']
                parsed = parse_reports({'ticker': ticker, 'analysisReports': raw}, ticker, latest_only=False)
                rows.extend(r for r in parsed if r['date'].year in years)
                if not raw or (isinstance(payload.get('total'), int) and (page + 1) * 100 >= payload['total']):
                    break
                # The public endpoint lists reports newest first.
                if parsed and min(r['date'].year for r in parsed) < years[-1]:
                    break
            else:
                raise ValueError('Lịch sử báo cáo vượt giới hạn tải')
        return sorted(rows, key=lambda r: r['date'], reverse=True)
    except (requests.RequestException, ValueError, TypeError, KeyError, AttributeError) as exc:
        raise EquityUnavailable(f'Chưa tải được báo cáo định giá {ticker} từ Simplize.') from exc


def broker_table(rows):
    esc = lambda value: html.escape(str(value), quote=True)
    body = []
    for row in rows:
        price = f"{row['price']:,.0f}".replace(',', '.') + ' VND' if row['price'] is not None else 'N/A'
        recommend = row['recommend'] or 'Chưa công bố'
        tone = 'buy' if recommend.upper() == 'MUA' else 'other'
        url = safe_url(row['url'])
        link = f'<a class="source-link" href="{esc(url)}" target="_blank" rel="noopener noreferrer" title="{esc(row["title"])}">Mở báo cáo ↗</a>' if url else '—'
        kind = 'Valuation Report' if row['price'] is not None else 'Recommendation'
        body.append(f'<tr data-year="{row["date"].year}" data-broker="{esc(row["broker"].casefold())}"><td><strong>{esc(row["broker"])}</strong></td>'
                    f'<td><span class="broker-kind">{kind}</span></td>'
                    f'<td class="broker-price" data-sort="{row["price"] if row["price"] is not None else ""}">{price}</td><td data-sort="{row["date"]:%Y-%m-%d}">{row["date"]:%d/%m/%Y}</td>'
                    f'<td>{esc(row["broker"])} — đăng trên Simplize</td>'
                    f'<td data-filter="{esc(recommend)}"><span class="broker-rating {tone}">{esc(recommend)}</span>'
                    f'<div class="broker-summary">{esc(row["title"])}</div></td><td>{link}</td></tr>')
    headers = ['CTCK', 'Loại báo cáo', 'Giá mục tiêu', 'Thời gian', 'Nguồn', 'Khuyến nghị & Giả định', 'Nguồn gốc']
    heading = ''.join(f'<th><button type="button" data-column="{i}" aria-label="{"Sắp xếp" if i == 2 else "Lọc"} {h}" aria-expanded="false" title="{"Sắp xếp tăng/giảm" if i == 2 else "Chọn một năm" if i == 3 else "Lọc giá trị trong cột"}">{h} <span>{"↕" if i == 2 else "▾"}</span></button></th>' if i not in (4, 6) else f'<th>{h}</th>' for i, h in enumerate(headers))
    return '<div class="source-table-wrap"><table class="source-table broker-table"><thead><tr>' + heading + '</tr></thead><tbody>' + ''.join(body) + '</tbody></table></div>'


def filterable_broker_document(rows, current_year=None):
    years = report_years(current_year)
    rows = [r for r in rows if r['date'].year in years]
    return '''<!doctype html><html lang="vi"><head><meta charset="utf-8"><style>
    :root { color-scheme: light dark; }
    body { margin:0; font:14px Arial,sans-serif; color:light-dark(#292524,#e8e3e0); background:transparent; }
    .source-table-wrap { overflow-x:auto; border:1px solid light-dark(#ded8d4,#494341); border-radius:12px; }
    table { width:100%; min-width:1050px; border-collapse:collapse; }
    th,td { padding:14px 12px; text-align:left; border-bottom:1px solid light-dark(#e8e2de,#494341); vertical-align:top; }
    th { font-size:11px; text-transform:uppercase; background:light-dark(#f3eeea,#302b29); }
    th button { font:inherit; text-transform:inherit; text-align:left; cursor:pointer; border:0; padding:0; color:inherit; background:transparent; }
    th button:focus-visible { outline:2px solid #6384db; outline-offset:4px; }
    .broker-price { color:light-dark(#4361b5,#9db6ff); font-weight:700; white-space:nowrap; }
    .broker-kind,.broker-rating { display:inline-block; padding:3px 9px; border-radius:12px; font-size:12px; background:rgba(90,120,200,.12); }
    .broker-rating.buy { color:light-dark(#227451,#8de1ba); background:rgba(60,180,120,.15); }
    .broker-summary { max-width:320px; margin-top:8px; font-size:12px; line-height:1.5; opacity:.8; }
    a { color:light-dark(#4361b5,#9db6ff); text-decoration:none; }
    .filter-menu { position:fixed; z-index:10; width:270px; padding:12px; box-sizing:border-box; border:1px solid light-dark(#d8d0ca,#655d58); border-radius:10px; background:light-dark(#fffaf6,#302b29); box-shadow:0 6px 20px #0003; }
    .filter-menu input[type=search] { width:100%; box-sizing:border-box; padding:8px; margin:8px 0; }
    .filter-options { max-height:180px; overflow:auto; }
    .filter-menu label { display:flex; gap:8px; align-items:center; padding:6px 0; overflow-wrap:anywhere; }
    [hidden] { display:none !important; }
    .filter-actions { display:flex; gap:8px; margin-top:10px; }
    .filter-actions button { cursor:pointer; padding:7px 12px; }
    button.active { color:light-dark(#4361b5,#9db6ff); }
    .filter-status { padding:10px 0; font-size:12px; }
    .source-table-wrap { max-height:650px; border-radius:14px; box-shadow:0 3px 12px #00000008; }
    table { table-layout:fixed; min-width:1080px; }
    th { position:sticky; top:0; z-index:2; font-size:12px; letter-spacing:.03em; padding:17px 14px; }
    td { padding:18px 14px; line-height:1.5; }
    th:nth-child(1) { width:85px; } th:nth-child(2) { width:125px; }
    th:nth-child(3) { width:130px; } th:nth-child(4) { width:110px; }
    th:nth-child(5) { width:150px; } th:nth-child(6) { width:260px; } th:nth-child(7) { width:120px; }
    tbody tr:nth-child(even) { background:light-dark(#faf7f4,#282422); }
    tbody tr:hover { background:light-dark(#f0f4fc,#31394a); }
    .broker-summary { font-size:13px; opacity:1; color:light-dark(#6a625d,#c5bdb7); }
    .broker-price { font-size:16px; font-variant-numeric:tabular-nums; }
    .filter-status { color:light-dark(#6a625d,#c5bdb7); }
    .filter-menu { max-height:360px; overflow:auto; }
    </style></head><body data-current-year="''' + str(years[0]) + '''">''' + broker_table(sorted(rows, key=lambda r: r['date'], reverse=True)) + '''<script>
    const table = document.querySelector('table'), body = table.tBodies[0];
    const rows = Array.from(body.rows), filters = new Map();
    const currentYear = Number(document.body.dataset.currentYear);
    const years = [currentYear, currentYear-1, currentYear-2].map(String);
    const availableYears = new Set(rows.map(row => row.dataset.year));
    let selectedYear = years.find(year => availableYears.has(year)) ?? years[0], priceDirection = null;
    const status = document.createElement('div');
    status.className = 'filter-status'; table.parentElement.after(status);
    const value = (row, column) => row.cells[column].dataset.filter ?? row.cells[column].textContent.trim();
    let menu = null, trigger = null;
    function closeMenu() {
      if (menu) menu.remove();
      if (trigger) trigger.setAttribute('aria-expanded','false');
      menu = null; trigger = null;
    }
    function applyFilters() {
      let count = 0, total = 0;
      const seen = new Set();
      rows.forEach(row => {
        const eligible = row.dataset.year === selectedYear && !seen.has(row.dataset.broker);
        if (eligible) { seen.add(row.dataset.broker); total++; }
        row.hidden = !eligible || !Array.from(filters).every(([column, selected]) => selected.has(value(row,column)));
        if (!row.hidden) count++;
      });
      table.querySelectorAll('button[data-column]').forEach(button => {
        const column = Number(button.dataset.column);
        if (column === 2) {
          button.querySelector('span').textContent = priceDirection === null ? '↕' : priceDirection === 'asc' ? '↑' : '↓';
          return;
        }
        if (column === 3) { button.querySelector('span').textContent = selectedYear + ' ▾'; return; }
        const active = filters.has(Number(button.dataset.column));
        button.classList.toggle('active',active);
        button.querySelector('span').textContent = active ? '⏷ ●' : '▾';
      });
      status.textContent = `Năm ${selectedYear} · Hiển thị ${count}/${total} CTCK · Báo cáo mới nhất của mỗi CTCK trong năm`;
      if (selectedYear !== years[0] && !availableYears.has(years[0])) status.textContent += ` · Nguồn chưa có báo cáo năm ${currentYear}`;
      if (count === 0) status.textContent += ' — Không có báo cáo khớp các bộ lọc.';
    }
    table.querySelectorAll('button[data-column]').forEach(button => {
      button.addEventListener('click', () => {
        const wasOpen = trigger === button;
        closeMenu(); if (wasOpen) return;
        const column = Number(button.dataset.column);
        if (column === 2) {
          priceDirection = priceDirection === 'asc' ? 'desc' : 'asc';
          const factor = priceDirection === 'asc' ? 1 : -1;
          [...rows].sort((a,b) => {
            const av=a.cells[2].dataset.sort, bv=b.cells[2].dataset.sort;
            if (av === '' || bv === '') return (av === '') - (bv === '');
            return (Number(av)-Number(bv))*factor;
          }).forEach(row => body.append(row));
          button.parentElement.setAttribute('aria-sort',priceDirection === 'asc' ? 'ascending' : 'descending');
          applyFilters(); return;
        }
        if (column === 3) {
          menu = document.createElement('div'); menu.className='filter-menu';
          menu.setAttribute('role','dialog'); menu.setAttribute('aria-label','Chọn năm');
          const heading=document.createElement('strong'); heading.textContent='Chọn một năm'; menu.append(heading);
          years.forEach(year => {
            const label=document.createElement('label'), radio=document.createElement('input');
            radio.type='radio'; radio.name='report-year'; radio.value=year; radio.checked=year===selectedYear;
            label.append(radio,document.createTextNode(year)); menu.append(label);
            radio.addEventListener('change',() => { selectedYear=year; applyFilters(); closeMenu(); button.focus(); });
          });
          trigger=button; button.setAttribute('aria-expanded','true'); document.body.append(menu);
          positionMenu(button); menu.querySelector('input:checked').focus(); return;
        }
        const values = [...new Set(rows.map(row => value(row,column)))];
        const selected = new Set(filters.get(column) ?? values);
        menu = document.createElement('div'); menu.className = 'filter-menu';
        menu.setAttribute('role','dialog'); menu.setAttribute('aria-label',button.getAttribute('aria-label'));
        menu.innerHTML = '<strong>Lọc giá trị</strong><input type="search" placeholder="Tìm trong cột…" aria-label="Tìm giá trị"><label><input type="checkbox" class="select-all">Chọn tất cả kết quả</label><div class="filter-options"></div><div class="filter-actions"><button class="apply">Áp dụng</button><button class="clear">Xóa lọc cột</button></div>';
        trigger = button; button.setAttribute('aria-expanded','true');
        const list = menu.querySelector('.filter-options'), search = menu.querySelector('input[type=search]');
        const all = menu.querySelector('.select-all');
        values.forEach(text => {
          const label = document.createElement('label'), input = document.createElement('input');
          input.type = 'checkbox'; input.checked = selected.has(text); input.dataset.value = text;
          label.append(input, document.createTextNode(text || '(Trống)')); list.append(label);
          input.addEventListener('change', () => {
            if (input.checked) selected.add(text); else selected.delete(text);
            updateAll();
          });
        });
        function matching() { return Array.from(list.querySelectorAll('input')).filter(input => !input.parentElement.hidden); }
        function updateAll() {
          const items = matching(), checked = items.filter(input => input.checked).length;
          all.checked = items.length > 0 && checked === items.length;
          all.indeterminate = checked > 0 && checked < items.length;
        }
        search.addEventListener('input', () => {
          list.querySelectorAll('label').forEach(label => { label.hidden = !label.textContent.toLocaleLowerCase('vi').includes(search.value.toLocaleLowerCase('vi')); });
          updateAll();
        });
        all.addEventListener('change', () => {
          matching().forEach(input => {
            input.checked = all.checked;
            if (all.checked) selected.add(input.dataset.value); else selected.delete(input.dataset.value);
          }); updateAll();
        });
        menu.querySelector('.apply').addEventListener('click', () => {
          if (selected.size === values.length) filters.delete(column); else filters.set(column,selected);
          applyFilters(); closeMenu(); button.focus();
        });
        menu.querySelector('.clear').addEventListener('click', () => {
          filters.delete(column); applyFilters(); closeMenu(); button.focus();
        });
        document.body.append(menu);
        positionMenu(button);
        updateAll(); search.focus();
      });
    });
    function positionMenu(button) {
      const rect=button.getBoundingClientRect();
      menu.style.left=Math.max(0,Math.min(rect.left,window.innerWidth-270))+'px';
      menu.style.top=Math.max(0,Math.min(rect.bottom+6,window.innerHeight-menu.offsetHeight))+'px';
    }
    document.addEventListener('click',event => { if (menu && !menu.contains(event.target) && !trigger.contains(event.target)) closeMenu(); });
    document.addEventListener('keydown',event => { if (event.key === 'Escape') { const button=trigger; closeMenu(); if(button) button.focus(); } });
    applyFilters();
    </script></body></html>'''
