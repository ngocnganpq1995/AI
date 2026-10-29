import unittest
from unittest.mock import patch, Mock
from financial_fallback import supplement
from news_cache import process_cached


class FallbackTests(unittest.TestCase):
    def test_overlap_preserves_valid_classification_chart(self):
        from ownership_chart import ownership_drawing
        from reportlab.graphics import renderSVG
        rows=[{'Cổ đông':'A','Tỷ lệ (%)':60},{'Cổ đông':'B','Tỷ lệ (%)':50}]
        groups=[{'Nhóm':'Sở hữu nước ngoài','Tỷ lệ (%)':3.21},{'Nhóm':'Sở hữu khác','Tỷ lệ (%)':96.79}]
        svg=renderSVG.drawToString(ownership_drawing(rows,groups,'VIC'))
        self.assertIn('96.79%',svg)
        self.assertIn('60.00%',svg)

    def test_units_periods_and_existing_zero(self):
        c={'ticker':'CMT','summary':{'epsRatio':None,'bookValue':0,'roe':None}}
        payloads=[{'Success':True,'Data':[{'Code':'EPScoBan','Value':'1.97'},
                  {'Code':'GiaTriSoSach','Value':'35.08'},{'Code':'ThoiGian','Value':'Quý IV năm 2024'}]},
                  {'Success':True,'Data':{'Value':[{'Year':2024,'Value':[{'Code':'ROE','Value':5.61}]}]}}]
        with patch('financial_fallback.requests.get',side_effect=[Mock(json=lambda p=p:p) for p in payloads]):
            supplement(c)
        self.assertEqual(c['summary'],{'epsRatio':1970,'bookValue':0,'roe':5.61})
        self.assertIn('2024',c['metric_notes']['roe'])

    def test_news_reuses_processing_but_updates_membership_and_expires(self):
        cache={}
        processor=Mock(side_effect=lambda item,*_:dict(item,article_text='content ' * 90))
        item={'url':'https://example.com/1','title':'News','summary':'Text','tickers':{'FPT'}}
        process_cached(item,False,'model',cache,processor,now=0)
        result=process_cached(dict(item,tickers={'FPT','CMG'}),False,'model',cache,processor,now=60)
        self.assertEqual(processor.call_count,1)
        self.assertEqual(result['tickers'],{'FPT','CMG'})
        process_cached(item,False,'model',cache,processor,now=901)
        self.assertEqual(processor.call_count,2)

    def test_short_article_is_retried_instead_of_cached(self):
        cache = {}
        processor = Mock(side_effect=lambda item,*_:dict(item,article_text='Only a short teaser'))
        item = {'url':'https://example.com/short','title':'News','summary':'Text'}
        process_cached(item,False,'model',cache,processor,now=0)
        process_cached(item,False,'model',cache,processor,now=60)
        self.assertEqual(processor.call_count,2)
        self.assertEqual(cache,{})
