"""Print-ready, portable four-section report with embedded Vietnamese font."""
from io import BytesIO
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle, Spacer, PageBreak, KeepTogether
from reportlab.graphics.shapes import Drawing, Line, PolyLine, Circle, Wedge, String

from equity_data import ownership_chart_rows, source_date, text_only
from ownership_chart import ownership_drawing

FONT = 'ReportVN'
ROSE = colors.HexColor('#88465f')
PALETTE = ['#88465f','#e4a4bd','#7a8e9c','#aa9984','#526b68','#c3afcc',
           '#89b4cf','#a5c9aa','#d4ab78','#a98199','#7188b0','#b8bf80','#d7d0cb']


class NewsTable(Table):
    """A continuation (and its repeated header) always starts a new page."""
    def split(self, availWidth, availHeight):
        parts = super().split(availWidth, availHeight)
        if len(parts) > 1:
            return [parts[0], PageBreak(), *parts[1:]]
        return parts


def news_report_rows(rows):
    return [{'Ngày':r.get('Ngày',''), 'Mã':r.get('Mã CK',''),
             'Tóm tắt thông tin':r.get('Tóm tắt thông tin',''),
             'Tiêu đề bài báo':r.get('Tiêu đề bài báo',''),
             'Nguồn / Loại tin':'\n'.join(str(r.get(k,'') or '') for k in ('Source','Loại tin'))}
            for r in rows]


def report_calendar_rows(bundle, calendar_month=None):
    months = sorted({r['Ngày'][:7] for r in bundle['events']}, reverse=True)
    month = calendar_month if calendar_month is not None else (months[0] if months else '')
    return month, [r for r in bundle['events'] if r['Ngày'][:7] == month]


def build_pdf(bundle, news_rows, searched_tickers, calendar_month=None, broker_reports=None):
    if FONT not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont(FONT, str(Path(__file__).parent/'assets/fonts/DejaVuSans.ttf')))
    output = BytesIO()
    page_w, page_h = landscape(A4)
    width = page_w-64
    doc = SimpleDocTemplate(output, pagesize=(page_w,page_h), leftMargin=32,rightMargin=32,
                            topMargin=32,bottomMargin=34, title=f'Stock News - {bundle["ticker"]}')
    body = ParagraphStyle('body',fontName=FONT,fontSize=9,leading=13,textColor=colors.HexColor('#262626'),spaceAfter=8)
    small = ParagraphStyle('small',parent=body,fontSize=8,leading=11,spaceAfter=0,splitLongWords=False)
    heading = ParagraphStyle('heading',parent=body,fontSize=20,leading=25,textColor=ROSE,spaceAfter=15)
    sub = ParagraphStyle('sub',parent=body,fontSize=12,leading=16,textColor=ROSE,spaceBefore=10,keepWithNext=True)
    story=[]
    def p(value,style=body):
        if value is None: value='—'
        if isinstance(value,float): value=f'{value:,.2f}'
        elif isinstance(value,int): value=f'{value:,}'
        return Paragraph(escape(str(value)).replace('\n','<br/>'),style)
    def section(title):
        if story: story.append(PageBreak())
        story.append(p(title,heading))
    def grid(rows,weights=None,news=False):
        if not rows:
            story.append(p('Chưa có dữ liệu từ nguồn tại thời điểm xuất.')); return
        keys=list(rows[0])
        weights=weights or [1]*len(keys)
        data=[[p(k,small) for k in keys]]
        for row in rows:
            data.append([p(row.get(k),small) for k in keys])
        table_class = NewsTable if news else Table
        tab=table_class(data,colWidths=[width*w/sum(weights) for w in weights],repeatRows=1,splitByRow=1,splitInRow=1)
        tab.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#f0e7e9')),
            ('VALIGN',(0,0),(-1,-1),'TOP'),('GRID',(0,0),(-1,-1),.35,colors.HexColor('#ded7d2')),
            ('LEFTPADDING',(0,0),(-1,-1),7),('RIGHTPADDING',(0,0),(-1,-1),7),
            ('TOPPADDING',(0,0),(-1,-1),7),('BOTTOMPADDING',(0,0),(-1,-1),7),
            ('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#fdf8f3')])]))
        story.extend([tab,Spacer(1,10)])
    def line_chart(frame,field,title,bars=False):
        if frame.empty:
            story.append(p('Chưa có dữ liệu giá.')); return
        d=Drawing(width,190)
        values=frame[field].astype(float).tolist()
        low,high=(0,max(values)) if bars else (min(values),max(values))
        span=high-low or 1
        pts=[(68+i*(width-90)/max(1,len(values)-1),30+(v-low)*125/span) for i,v in enumerate(values)]
        d.add(String(68,174,title,fontName=FONT,fontSize=10,fillColor=ROSE))
        for frac in (0,.5,1):
            y=30+125*frac
            d.add(Line(68,y,width-18,y,strokeColor=colors.HexColor('#e6deda'),strokeWidth=.5))
            d.add(String(0,y-3,f'{low+span*frac:,.0f}',fontName=FONT,fontSize=8))
        if bars:
            for x,y in pts: d.add(Line(x,30,x,y,strokeColor=ROSE,strokeWidth=2))
        else: d.add(PolyLine([n for xy in pts for n in xy],strokeColor=ROSE,strokeWidth=1.5))
        d.add(String(68,10,frame.date.min().strftime('%d/%m/%Y'),fontName=FONT,fontSize=8))
        d.add(String(width-85,10,frame.date.max().strftime('%d/%m/%Y'),fontName=FONT,fontSize=8))
        story.append(d)
    section('I / Tin chứng khoán')
    now=datetime.now(ZoneInfo('Asia/Ho_Chi_Minh')).strftime('%d/%m/%Y %H:%M UTC+7')
    story.append(p(f'Xuất lúc {now}. Tin đã quét: {", ".join(searched_tickers)}. Mục II-IV: {bundle["ticker"]}.'))
    story.append(p('Nguồn: Google News / báo gốc (tin), Simplize (lịch và định giá), Yahoo Finance (giá), CafeF (cổ đông). Dữ liệu có thể trễ hoặc thiếu.'))
    for error in bundle['errors']: story.append(p(error))
    grid(news_report_rows(news_rows),[10,6,40,27,17],news=True)
    section(f'II / Lịch doanh nghiệp - {bundle["ticker"]}')
    month, selected_events = report_calendar_rows(bundle, calendar_month)
    story.append(p(f'Tháng đang tra cứu: {month[5:7]}/{month[:4]}' if month else 'Chưa có tháng tra cứu.'))
    story.append(p('Lịch theo nguồn công khai. Ngày công bố không thay thế ngày thực hiện; ngày đã qua không xác nhận hoàn tất.'))
    events=[{k:r.get(k) for k in ['Ngày','Sự kiện','Nhóm','Loại ngày']} for r in selected_events]
    grid(events,[12,48,18,22])
    section(f'III / Giá cổ phiếu - {bundle["ticker"]}')
    story.append(p(' · '.join(str(v) for v in bundle['price_meta'].values())))
    line_chart(bundle['prices'],'close','Giá đóng cửa (VND/cổ phiếu)')
    line_chart(bundle['prices'],'volume','Khối lượng (cổ phiếu)',True)
    chart=ownership_chart_rows(bundle['ownership'])
    if chart or bundle.get('ownership_groups'):
        d=ownership_drawing(bundle['ownership'],bundle.get('ownership_groups',[]),bundle['ticker'])
        scale=width/d.width
        d.scale(scale,scale); d.width*=scale; d.height*=scale
        story.append(d)
    else:
        story.append(p('Cơ cấu sở hữu - CafeF',sub))
        story.append(p('Chưa đủ dữ liệu để vẽ biểu đồ tròn hoặc tổng tỷ lệ công bố vượt 100%.'))
    story.append(p('Nguồn CafeF. Vòng ngoài: cổ đông từ 1% và phần còn lại; vòng trong: phân loại sở hữu. Nhãn giữ tỷ lệ gốc; kích thước lát chia theo tổng dữ liệu như CafeF. Công bố có thể khác ngày, chồng lặp và cộng vượt 100%.'))
    section(f'IV / Định giá - {bundle["ticker"]}')
    story.append(p('Tối đa 10 mã đối chiếu cùng nhóm ngành ngoài mã đang tra, ưu tiên vốn hóa lớn trong danh sách nguồn trả về. P/E: TTM; P/B: quý gần nhất.'))
    cols=['Mã','Doanh nghiệp','P/E (TTM)','P/B (FQ)','Vốn hóa (tỷ đồng)','Nguồn cập nhật']
    grid([{k:r.get(k) for k in cols} for r in bundle['peers']],[7,34,12,12,19,16])
    story.append(p('Chỉ số bổ sung',sub))
    cols=['Mã','Giá tham chiếu nguồn (đ/CP)','EPS (TTM, đ/CP)','BVPS (đ/CP)','ROE (%)']
    grid([{('EPS (đ/CP)' if k == 'EPS (TTM, đ/CP)' else k):r.get(k) for k in cols} for r in bundle['peers']],[10,27,25,25,13])
    for row in bundle['peers']:
        if row.get('Kỳ số liệu bổ sung'):
            story.append(p(f"{row['Mã']} · {row['Kỳ số liệu bổ sung']}"))
    story.append(p('Chỉ số bổ sung từ CafeF có thể thuộc kỳ cũ; không dùng các giá trị này để tính tham chiếu tương đối với bội số hiện tại.'))
    story.append(p('Tham chiếu tương đối',sub))
    story.append(p('EPS × trung vị P/E hoặc BVPS × trung vị P/B của các mã đối chiếu; loại mã đang tra và bội số không dương, cần ít nhất 2 mã. Không phải khuyến nghị đầu tư.'))
    grid(bundle['relative'])
    story.append(p('Chỉ số thấp chưa đủ để kết luận cổ phiếu rẻ.'))
    section(f'V / Báo cáo định giá CTCK - {bundle["ticker"]}')
    story.append(p('Báo cáo mới nhất của mỗi công ty chứng khoán trong ba năm gần nhất theo Simplize. Giá mục tiêu theo nguồn (VND/cổ phiếu); N/A khi chưa công bố. Nội dung là tiêu đề báo cáo; xem báo cáo gốc để biết giả định chi tiết.'))
    broker_cols=['CTCK','Loại báo cáo','Giá mục tiêu (VND/CP)','Ngày','Nguồn','Khuyến nghị & giả định']
    broker_rows=[]
    for row in (broker_reports or []):
        price=row.get('price')
        price_text=f'{price:,.0f}'.replace(',', '.')+' VND' if price is not None else 'N/A'
        published=row.get('date')
        date_text=published.strftime('%d/%m/%Y') if hasattr(published,'strftime') else str(published or '—')
        broker_rows.append({'CTCK':row.get('broker'),'Loại báo cáo':'Valuation Report' if price is not None else 'Recommendation',
            'Giá mục tiêu (VND/CP)':price_text,'Ngày':date_text,
            'Nguồn':f"{row.get('broker')} — đăng trên Simplize",
            'Khuyến nghị & giả định':' · '.join(filter(None,[row.get('recommend'),row.get('title')])) or 'Chưa công bố'})
    grid(broker_rows,[12,17,17,13,19,34])
    story.append(p('Nguồn gốc: Simplize. Báo cáo gốc được liên kết trong bảng trên giao diện; PDF ghi lại thông tin báo cáo và tiêu đề.'))
    def footer(canvas,document):
        canvas.setFont(FONT,8); canvas.setFillColor(ROSE)
        canvas.drawString(32,18,f'Stock News | {bundle["ticker"]} | {now}')
        canvas.drawRightString(page_w-32,18,f'Trang {document.page}')
    doc.build(story,onFirstPage=footer,onLaterPages=footer)
    return output.getvalue()
