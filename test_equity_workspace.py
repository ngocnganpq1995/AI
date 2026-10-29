import unittest
from unittest.mock import patch
from pathlib import Path
from streamlit.testing.v1 import AppTest
from equity_fixture import make_bundle
from equity_data import company_events, comparable_rows, relative_valuation, source_date, EquityUnavailable, parse_cafef_ownership, ownership_chart_rows
from equity_report import build_report
from equity_pdf import build_pdf, news_report_rows, report_calendar_rows
from news_content import news_table


class EquityTests(unittest.TestCase):
    def test_cafef_two_ring_data_and_one_percent_threshold(self):
        from equity_data import parse_ownership_structure
        from ownership_chart import ownership_drawing
        from reportlab.graphics import renderSVG
        raw={'CoDongSoHuu':[{'Name':'Cổ đông A','AssetRate':'25,8','AssetVolume':'2.178.000','UpdatedDate':'25/05/2026'},
                            {'Name':'Cổ đông nhỏ','AssetRate':'0,9','AssetVolume':'900','UpdatedDate':'25/05/2026'}],
             'NuocNgoai':21.74,'NhaNuoc':0,'Khac':78.26}
        parsed=parse_ownership_structure(raw,'HPG')
        self.assertEqual(parsed['groups'][0]['Tỷ lệ (%)'],21.74)
        outer=ownership_chart_rows(parsed['rows'])
        self.assertEqual(len(outer),2)
        self.assertEqual(outer[-1]['Tỷ lệ (%)'],74.2)
        svg=renderSVG.drawToString(ownership_drawing(parsed['rows'],parsed['groups'],'HPG'))
        self.assertIn('21.74%',svg)
        self.assertIn('78.26%',svg)
        raw['NuocNgoai']=None
        self.assertEqual(parse_ownership_structure(raw,'HPG')['groups'],[])

    def test_ownership_chart_shortens_long_labels(self):
        from ownership_chart import ownership_drawing
        from reportlab.graphics import renderSVG
        long_name = 'Cổ đông có tên rất dài để kiểm tra việc không bị tràn chữ trên biểu đồ'
        svg = renderSVG.drawToString(ownership_drawing([{'Cổ đông': long_name, 'Tỷ lệ (%)': 25}], [], 'PNJ'))
        self.assertNotIn(long_name, svg)
        self.assertIn('…', svg)

    def test_pdf_calendar_matches_selected_month(self):
        bundle=make_bundle()
        month, rows=report_calendar_rows(bundle,'2026-05')
        self.assertEqual(month,'2026-05')
        self.assertEqual(len(rows),2)
        self.assertTrue(all(r['Ngày'].startswith('2026-05') for r in rows))
        self.assertEqual(report_calendar_rows(bundle,'2026-04')[1],[])
        self.assertEqual(report_calendar_rows(bundle)[0],'2026-06')
        app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py'),default_timeout=30)
        app.session_state['profile_ready']=True
        with patch('equity_views.load_equity',side_effect=make_bundle), patch('equity_pdf.build_pdf',return_value=b'%PDF-test') as export:
            app.run()
            self.assertFalse(app.exception)
            self.assertEqual(export.call_args.kwargs['calendar_month'],'2026-06')
            app.selectbox(key='equity_month_FPT').select('2026-05').run()
            self.assertFalse(app.exception)
            self.assertEqual(export.call_args.kwargs['calendar_month'],'2026-05')

    def test_pdf_news_columns_and_embedded_graphics(self):
        row={'Ngày':'17/09/2026','Mã CK':'HPG','Source':'CafeF','Loại tin':'Doanh nghiệp',
             'Tóm tắt thông tin':'Nội dung tiếng Việt & số liệu. '*150,'Tiêu đề bài báo':'Tiêu đề kiểm tra',
             'Đọc tin gốc':'https://example.com','Tình trạng nguồn':'Đã tải'}
        normalized=news_report_rows([row])[0]
        self.assertEqual(list(normalized),['Ngày','Mã','Tóm tắt thông tin','Tiêu đề bài báo','Nguồn / Loại tin'])
        self.assertEqual(normalized['Nguồn / Loại tin'],'CafeF\nDoanh nghiệp')
        pdf=build_pdf(make_bundle('HPG'),[row],['HPG'])
        self.assertTrue(pdf.startswith(b'%PDF-'))
        self.assertIn(b'/FontFile2',pdf)

    def test_top_ten_peers_sorted_by_market_cap(self):
        c=make_bundle()['company']
        candidates=[{'ticker':f'A{i}','marketCapVnd':i*1e9} for i in range(14)]
        def fetch(code):
            other=make_bundle(code)['company']; other['summary']['marketCap']=int(code[1:])*1e9
            return other
        rows,_=comparable_rows(c,fetch,lambda _:candidates)
        self.assertEqual(len(rows),11)
        self.assertEqual([r['Mã'] for r in rows[1:]],['A'+str(i) for i in range(13,3,-1)])

    def test_cafef_shareholders_and_invalid_pie_total(self):
        markup='<table><tr><td>Trần Đình Long</td><td>2.178.000.179</td><td>25,8</td><td>25/05/2026</td></tr><tr><td>Chủ tịch</td><td>Tên</td><td>65</td><td>Chi tiết</td></tr></table>'
        rows=parse_cafef_ownership(markup,'HPG')
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['Số cổ phiếu'],2178000179)
        self.assertEqual(rows[0]['Tỷ lệ (%)'],25.8)
        self.assertEqual(ownership_chart_rows(rows)[-1]['Tỷ lệ (%)'],74.2)
        self.assertEqual(len(ownership_chart_rows(rows*4)),4)
        with self.assertRaises(EquityUnavailable):
            parse_cafef_ownership('<html>Unavailable</html>','HPG')

    def test_dates_are_distinct_and_publication_never_becomes_execution(self):
        bundle=make_bundle()
        self.assertEqual([e['Ngày'] for e in bundle['events']],['2026-06-10','2026-05-29','2026-05-28'])
        c=bundle['company']
        c['companyNews']=[{'title':'Phát hành thêm','createdDate':'12/09/2026','executionDate':''}]
        event=company_events(c)[0]
        self.assertEqual(event['Loại ngày'],'Ngày công bố (không phải ngày thực hiện)')
        self.assertEqual(source_date('01/12/2025'),'2025-12-01')
        self.assertEqual(source_date('31/02/2025'),'')

    def test_peers_must_match_industry_and_target_excluded(self):
        c=make_bundle()['company']; c['stocks']=[{'ticker':'CMG'},{'ticker':'BANK'}]
        def fetch(code):
            other=make_bundle(code)['company']
            if code=='BANK': other['summary']['bcIndustryGroupId']=99
            return other
        rows,_=comparable_rows(c,fetch)
        self.assertEqual([r['Mã'] for r in rows],['FPT','CMG'])
        rows=make_bundle()['peers']; rows[0]['P/E (TTM)']=999
        self.assertEqual(relative_valuation(rows)[0]['Trung vị nhóm'],15)
        rows[0]['EPS (TTM, đ/CP)']=-1
        self.assertEqual([r['Phương pháp'] for r in relative_valuation(rows)],['P/B (FQ)'])
        rows[1]['P/B (FQ)']=None
        self.assertEqual(relative_valuation(rows),[])

    def test_report_is_portable_safe_and_contains_all_sections(self):
        b=make_bundle(); b['events'][0]['Sự kiện']='<script>alert(1)</script>'
        report=build_report(b,[{'Tiêu đề':'<img src=x onerror=alert(1)>','Nguồn':'javascript:alert(1)'}],['FPT'])
        for label in ['I / Stock News','II / Lịch doanh nghiệp','III / Giá cổ phiếu','IV / Định giá']:
            self.assertIn(label,report)
        self.assertIn('<svg',report)
        self.assertNotIn('<script',report)
        self.assertNotIn('<img',report)
        self.assertNotIn('href="javascript:',report)

    def test_auto_loading_and_switching_ticker_without_price_button(self):
        app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py'),default_timeout=30)
        app.session_state['profile_ready']=True
        with patch('equity_views.load_equity',side_effect=make_bundle) as load:
            app.run()
            self.assertFalse(app.exception)
            load.assert_called_with('FPT','3mo')
            self.assertNotIn('Tải biểu đồ giá',[b.label for b in app.button])
            self.assertFalse(any('### Lịch sử chia cổ tức' in m.value or '### Phát hành thêm & thưởng cổ phiếu' in m.value for m in app.markdown))
            app.selectbox(key='equity_ticker').select('TCB').run()
            self.assertFalse(app.exception)
            load.assert_called_with('TCB','3mo')
            self.assertTrue(any('Định giá · TCB' in m.value for m in app.markdown))
            app.selectbox(key='equity_ticker_prices').select('VIC').run()
            self.assertFalse(app.exception)
            self.assertEqual(app.selectbox(key='equity_ticker').value,'VIC')
            self.assertEqual(app.selectbox(key='equity_ticker_valuation').value,'VIC')
            load.assert_called_with('VIC','3mo')

    def test_news_title_column_precedes_source(self):
        row={'Ngày':'2026-09-17','Mã CK':'FPT','Tóm tắt thông tin':'Tóm tắt','Tiêu đề bài báo':'Tiêu đề',
             'Source':'Nguồn','Loại tin':'Doanh nghiệp','Đọc tin gốc':'https://example.com'}
        rendered=news_table([row])
        self.assertLess(rendered.index('<th scope="col">Tiêu đề bài báo'), rendered.index('<th scope="col">Tóm tắt'))
        self.assertNotIn('<th scope="col">Nguồn',rendered)
        self.assertIn('href="#news-detail-1"',rendered)
