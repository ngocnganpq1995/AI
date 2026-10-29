"""Shared CafeF-style two-ring vector chart for the app and PDF."""
import math
import textwrap
from pathlib import Path
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.graphics.shapes import Drawing, Wedge, Circle, String, PolyLine
from equity_data import ownership_chart_rows

FONT='ReportVN'
PALETTE=['#8cb5ef','#46464e','#a3eb71','#efa351','#8985e8','#dd5886','#dcd84c','#4c9397','#df6068','#a2e6dc','#bbc0c7','#818181','#f1cd63','#7898ce']

def ownership_drawing(rows, groups, ticker):
    if FONT not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont(FONT,str(Path(__file__).parent/'assets/fonts/DejaVuSans.ttf')))
    chart=ownership_chart_rows(rows)
    d=Drawing(1100,640)
    cx,cy,r=550,335,145
    def text(x,y,value,size=12,color='#262626',anchor='start'):
        d.add(String(x,y,value,fontName=FONT,fontSize=size,fillColor=colors.HexColor(color),textAnchor=anchor))
    def short_label(value, limit=30):
        value = ' '.join(str(value).split())
        return value if len(value) <= limit else value[:limit - 1].rstrip() + '…'
    text(cx,617,'Biểu đồ cơ cấu sở hữu',14,'#616875',anchor='middle')
    title = 'Tập đoàn Vingroup - Công ty Cổ phần (VIC)' if ticker == 'VIC' else f'Cơ cấu sở hữu · {ticker}'
    text(cx,590,title,18,anchor='middle')
    sides={-1:[],1:[]}; angle=90
    total = sum(row['Tỷ lệ (%)'] for row in chart) or 100
    visible_labels = set(range(min(11,len(chart))))
    if len(chart)>11:
        # Resolve equal-size crowded labels consistently, keeping the last tie.
        ties = [i for i,row in enumerate(chart) if row['Tỷ lệ (%)'] == chart[10]['Tỷ lệ (%)']]
        visible_labels.discard(10)
        visible_labels.add(ties[-1])
    for i,row in enumerate(chart):
        # Highcharts pie normalizes arc geometry to its series total; labels retain source values.
        sweep=row['Tỷ lệ (%)']/total*360; color=PALETTE[i%len(PALETTE)]
        d.add(Wedge(cx,cy,r,angle-sweep,angle,fillColor=colors.HexColor(color),strokeColor=colors.white,strokeWidth=1))
        mid=math.radians(angle-sweep/2); side=1 if math.cos(mid)>=0 else -1
        if i in visible_labels or row['Cổ đông'] == 'Khác / phần còn lại':
            sides[side].append((cy+math.sin(mid)*r,mid,row,color))
        angle-=sweep
    d.add(Circle(cx,cy,90,fillColor=colors.white,strokeColor=colors.white))
    angle=90; inner_colors=['#244575','#40308c','#40968d']
    nonzero=[g for g in groups if g['Tỷ lệ (%)']>0]
    if not chart and nonzero:
        text(cx,565,'Phân loại sở hữu từ CafeF',13,anchor='middle')
        text(cx,530,'Danh sách cổ đông có tỷ lệ chồng lặp; không vẽ vòng ngoài.',11,anchor='middle')
    for i,g in enumerate(nonzero):
        sweep=g['Tỷ lệ (%)']*3.6; color=inner_colors[i%3]
        d.add(Wedge(cx,cy,73 if chart else 145,angle-sweep,angle,fillColor=colors.HexColor(color),strokeColor=colors.white,strokeWidth=1))
        mid=math.radians(angle-sweep/2)
        if g['Tỷ lệ (%)'] >= 8:
            label_radius = 43 if chart else 80
            text(cx+math.cos(mid)*label_radius,cy+math.sin(mid)*label_radius-4,f"{g['Tỷ lệ (%)']:.2f}%",11,'#ffffff','middle')
        angle-=sweep
    if not nonzero:
        text(cx,cy,'Chưa có phân loại',9,anchor='middle')
    for side,labels in sides.items():
        labels.sort(reverse=True,key=lambda x:x[0])
        positions = []
        for natural_y,mid,row,color in labels:
            desired = cy + math.sin(mid)*225
            positions.append(min(535, desired, positions[-1]-48 if positions else 535))
        if positions and positions[-1]<125:
            shift=125-positions[-1]
            positions=[y+shift for y in positions]
        for j,(_,mid,row,color) in enumerate(labels):
            y=positions[j]
            edge=cx+side*175; tx=cx+side*195
            d.add(PolyLine([cx+r*math.cos(mid),cy+r*math.sin(mid),edge,y,tx-side*8,y],strokeColor=colors.HexColor(color),strokeWidth=.8))
            lines=(textwrap.wrap(short_label(row['Cổ đông']),width=25) or [''])[:2]
            for k,line in enumerate(lines): text(tx,y-k*12,line,9,anchor='start' if side==1 else 'end')
            text(tx,y-len(lines)*13,f"{row['Tỷ lệ (%)']:.2f}%",10,'#616875','start' if side==1 else 'end')
    for i,g in enumerate(nonzero):
        x=90+i*350
        d.add(Circle(x,40,6,fillColor=colors.HexColor(inner_colors[i%3]),strokeColor=None))
        text(x+14,36,f"{short_label(g['Nhóm'], 27)} ({g['Tỷ lệ (%)']:.2f}%)",10)
    return d
