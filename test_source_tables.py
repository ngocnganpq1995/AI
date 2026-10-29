import unittest
from source_tables import source_table


class SourceTableTests(unittest.TestCase):
    def test_merge_sources_escape_content_and_hide_period_column(self):
        rendered=source_table([{'Mã':'<script>','EPS (TTM, đ/CP)':1970.,
            'Kỳ số liệu bổ sung':'2024','Nguồn':'https://simplize.vn/co-phieu/CMT',
            'Nguồn bổ sung':'https://cafef.vn/test','Chỉ số bổ sung':'epsRatio'}])
        self.assertEqual(rendered.count('<th>Mở nguồn</th>'),1)
        self.assertIn('Simplize ↗',rendered)
        self.assertIn('CafeF ↗',rendered)
        self.assertNotIn('Kỳ số liệu bổ sung',rendered)
        self.assertNotIn('<script>',rendered)
        self.assertIn('target="_blank"',rendered)

    def test_invalid_links_never_render(self):
        rendered=source_table([{'Ngày':'2026-09-20','Nguồn':'javascript:alert(1)'}])
        self.assertNotIn('href=',rendered)
