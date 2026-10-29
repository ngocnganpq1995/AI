"""Portable HTML report: inline SVG charts, escaped tables, no external scripts."""
from datetime import date, datetime
from zoneinfo import ZoneInfo
import html
import pandas as pd
from investor_events import safe_url
from equity_data import source_date, text_only, ownership_chart_rows
from equity_pdf import news_report_rows, report_calendar_rows


def ownership_svg(rows):
    chart = ownership_chart_rows(rows)
    if not chart:
        return ""
    colors = ["#88465f", "#e4a4bd", "#7a8e9c", "#aa9984", "#526b68", "#c3afcc"]
    parts, offset = [], 0
    for i, row in enumerate(chart):
        pct = row['Tỷ lệ (%)']
        color = colors[i % len(colors)]
        parts.append(f'<circle cx="150" cy="150" r="100" fill="none" stroke="{color}" stroke-width="48" pathLength="100" stroke-dasharray="{pct} {100-pct}" stroke-dashoffset="{-offset}" transform="rotate(-90 150 150)"/>')
        parts.append(f'<text x="310" y="{22+i*24}" fill="{color}">{html.escape(row["Cổ đông"])} · {pct:.2f}%</text>')
        offset += pct
    return '<svg viewBox="0 0 1000 340" role="img" aria-label="Cơ cấu sở hữu CafeF">'+''.join(parts)+'</svg>'


def table(rows):
    if not rows:
        return '<p class="muted">Chưa có dữ liệu từ nguồn tại thời điểm xuất.</p>'
    frame = pd.DataFrame(rows)
    headers = ''.join('<th>'+html.escape(str(k))+'</th>' for k in frame.columns)
    body=[]
    for _, row in frame.iterrows():
        cells=[]
        for key,value in row.items():
            if value is None or (isinstance(value,float) and pd.isna(value)):
                value='—'
            text=html.escape(str(value))
            if key in ('Nguồn','Đọc tin gốc') and safe_url(str(value)):
                text=f'<a href="{html.escape(str(value),quote=True)}" rel="noopener noreferrer">Mở nguồn</a>'
            cells.append('<td>'+text+'</td>')
        body.append('<tr>'+''.join(cells)+'</tr>')
    return '<div class="table-wrap"><table><thead><tr>'+headers+'</tr></thead><tbody>'+''.join(body)+'</tbody></table></div>'


def svg_chart(frame, field, title, bars=False):
    if frame.empty:
        return '<p>Chưa tải được biểu đồ.</p>'
    values=frame[field].astype(float).tolist()
    low,high=(0,max(values)) if bars else (min(values),max(values))
    span=high-low or 1
    points=[(75+i*760/max(1,len(values)-1),230-(v-low)/span*185) for i,v in enumerate(values)]
    if bars:
        graph=''.join(f'<line x1="{x:.2f}" y1="230" x2="{x:.2f}" y2="{y:.2f}" stroke="#e4a4bd" stroke-width="3"/>' for x,y in points)
    else:
        graph='<polyline fill="none" stroke="#88465f" stroke-width="2" points="'+' '.join(f'{x:.2f},{y:.2f}' for x,y in points)+'"/>'
    return f'''<svg viewBox="0 0 900 280" role="img" aria-label="{html.escape(title,quote=True)}">
    <text x="75" y="22">{html.escape(title)}</text><text x="4" y="50">{high:,.0f}</text>
    <text x="4" y="230">{low:,.0f}</text><path d="M75 35V230H845" fill="none" stroke="#aaa"/>
    {graph}<text x="75" y="258">{frame.date.min():%d/%m/%Y}</text><text x="745" y="258">{frame.date.max():%d/%m/%Y}</text></svg>'''


def build_report(bundle, news_rows, searched_tickers, calendar_month=None):
    month, selected_events = report_calendar_rows(bundle, calendar_month)
    ticker=html.escape(bundle['ticker'])
    company=bundle['company']
    provenance=(f'Simplize · cập nhật trang: {company["summary"].get("analysisUpdated","chưa rõ")} · tải {company["fetched"]}' if company else 'Chưa có hồ sơ doanh nghiệp')
    price_note=' · '.join(str(v) for v in bundle['price_meta'].values())
    errors=''.join('<p>'+html.escape(e)+'</p>' for e in bundle['errors'])
    now=datetime.now(ZoneInfo('Asia/Ho_Chi_Minh')).strftime('%d/%m/%Y %H:%M (UTC+7)')
    return f'''<!doctype html><html lang="vi"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
    <title>Stock News — {ticker}</title><style>
    body{{font:15px/1.6 Arial,sans-serif;color:#262626;background:#fdf8f3;max-width:1200px;margin:auto;padding:32px}}
    h1,h2{{color:#88465f}}section{{margin:40px 0;break-before:page}}.muted,footer{{color:#6b625d}}
    table{{border-collapse:collapse;width:100%;font-size:12px}}th,td{{padding:9px;border:1px solid #ddd;text-align:left;overflow-wrap:anywhere}}
    th{{background:#f5f0eb}}.table-wrap{{overflow:auto}}a{{color:#88465f}}svg{{width:100%;max-height:310px}}svg text{{font:12px Arial}}
    @media print{{body{{background:white;padding:0}}.table-wrap{{overflow:visible}}thead{{display:table-header-group}}tr{{break-inside:avoid}}}}
    </style><h1>Stock News · Báo cáo {ticker}</h1><p>Xuất lúc {now}</p>
    <p>Tab I: tin đã quét cho {html.escape(', '.join(searched_tickers))}. Tab II–IV: mã {ticker}, khoảng giá {html.escape(bundle['period'])}.</p>
    <p>{html.escape(provenance)}</p><p>Bản chụp dữ liệu khi xuất; mở bằng trình duyệt, dùng Ctrl+P để lưu PDF. Dữ liệu thiếu được ghi rõ, không điền số 0 thay thế.</p>{errors}
    <section><h2>I / Stock News</h2>{table(news_report_rows(news_rows))}</section>
    <section><h2>II / Lịch doanh nghiệp</h2><p>Tháng đang tra cứu: {html.escape(month)}. Cột Loại ngày phân biệt ngày công bố, chốt quyền và thực hiện. Không coi ngày đã qua là xác nhận hoàn tất.</p>{table(selected_events)}</section>
    <section><h2>III / Giá cổ phiếu</h2><p>{html.escape(price_note)}</p>
    {svg_chart(bundle['prices'],'close','Giá (VND/cổ phiếu)')}{svg_chart(bundle['prices'],'volume','Khối lượng (cổ phiếu)',True)}
    <h3>Cơ cấu sở hữu · CafeF</h3><p>Ngày cập nhật riêng cho từng cổ đông; công bố có thể khác thời điểm hoặc chồng lặp. Biểu đồ: 12 cổ đông lớn nhất, phần còn lại = 100% trừ tỷ lệ hiển thị. Chưa có tỷ lệ sở hữu nước ngoài xác minh được.</p>{ownership_svg(bundle['ownership'])}{table(bundle['ownership'])}
    <h3>Dữ liệu giá</h3>{table(bundle['prices'].assign(date=bundle['prices'].date.dt.strftime('%Y-%m-%d')).to_dict('records') if not bundle['prices'].empty else [])}</section>
    <section><h2>IV / Định giá</h2><p>P/E: TTM · P/B: quý gần nhất. Mẫu cùng nhóm ngành, không phải toàn ngành.</p>{table(bundle['peers'])}
    <h3>Tham chiếu tương đối</h3><p>EPS × trung vị P/E hoặc BVPS × trung vị P/B; loại mã đang tra và bội số không dương, cần ít nhất 2 mã. Đây là phép tính của app, không phải giá mục tiêu từ báo cáo.</p>{table(bundle['relative'])}
    </section>
    <footer>Dữ liệu tham khảo có thể trễ hoặc thiếu. Bội số thấp chưa đủ để kết luận cổ phiếu rẻ.</footer></html>'''
