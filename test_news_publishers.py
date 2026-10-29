import unittest
from unittest.mock import Mock, patch
import requests
from news_publishers import (_sitemap, publisher_catalog_article, disclosure_article,
                             split_title, _candidates)


def response(body, url='https://cafef.vn/story.chn'):
    return Mock(content=body.encode(), url=url, raise_for_status=Mock())


class PublisherTests(unittest.TestCase):
    @patch('news_fetch.requests.get')
    def test_sidebar_pdf_is_not_treated_as_article_evidence(self, get):
        from news_fetch import article_document
        document = '<div class="KenhF_Content_News3"><p>Short company notice.</p></div><aside><a href="https://cafefnew.mediacdn.vn/other.pdf">Unrelated report</a></aside>'
        article_document(document, 'Company notice', 'https://cafef.vn/story.chn')
        get.assert_not_called()

    def test_editor_body_is_not_replaced_by_nested_related_preview(self):
        from news_content import extract_article
        text = 'Doanh nghiệp tăng sản lượng nhưng chi phí nguyên liệu ảnh hưởng đến lợi nhuận. ' * 12
        document = f'<div class="detail-content"><div id="explus-editor"><p>{text}</p></div><div class="news-content">Related story preview</div></div>'
        self.assertIn(text.strip(), extract_article(document))

    def setUp(self):
        _sitemap.cache_clear()

    def test_publisher_name_can_contain_separator(self):
        self.assertEqual(split_title('Sự kiện ngày 21/9 - Tạp chí Kinh tế - Tài chính Online'),
                         ('Sự kiện ngày 21/9', 'tạp chí kinh tế - tài chính online'))

    @patch('news_publishers.requests.get')
    def test_catalog_verifies_headline_after_partial_slug_match(self, get):
        title = 'Chuyện gì đây: Chứng khoán SSI treo thưởng iPhone 18'
        url = 'https://cafef.vn/chung-khoan-ssi-treo-thuong-iphone-18-123.chn'
        get.side_effect = [response(f'<urlset><url><loc>{url}</loc></url></urlset>'),
                           response(f'<h1>{title}</h1><article>Content</article>')]
        self.assertEqual(publisher_catalog_article(title + ' - cafef.vn')[0], url)

    @patch('news_publishers.requests.get')
    def test_candidate_with_similar_title_is_rejected(self, get):
        url = 'https://cafef.vn/ssi-loi-nhuan-quy-iii-tang-manh-123.chn'
        get.side_effect = [response(f'<urlset><url><loc>{url}</loc></url></urlset>'),
                           response('<h1>SSI lợi nhuận quý III giảm mạnh</h1>')]
        self.assertIsNone(publisher_catalog_article('SSI lợi nhuận quý III tăng mạnh - cafef.vn'))

    @patch('news_publishers.requests.get')
    def test_cross_domain_sitemap_links_are_not_fetched(self, get):
        get.return_value = response('<urlset><url><loc>https://other.test/ssi-loi-nhuan-quy-iii</loc></url></urlset>')
        self.assertIsNone(publisher_catalog_article('SSI lợi nhuận quý III - cafef.vn'))
        self.assertEqual(get.call_count, 1)

    @patch('news_publishers.requests.get')
    def test_recent_archive_uses_date_in_path_not_misleading_lastmod(self, get):
        recent = 'https://cafef.vn/sitemap-2026-09-21.xml'
        old = 'https://cafef.vn/sitemap-2022-11-17.xml'
        url = 'https://cafef.vn/ssi-loi-nhuan-quy-iii-123.chn'
        get.side_effect = [response(f'<sitemapindex><sitemap><loc>{old}</loc><lastmod>2099-01-01</lastmod></sitemap><sitemap><loc>{recent}</loc><lastmod>2026-09-21</lastmod></sitemap></sitemapindex>'),
                           response(f'<urlset><url><loc>{url}</loc></url></urlset>'),
                           response('<h1>SSI lợi nhuận quý III</h1>')]
        self.assertIsNotNone(publisher_catalog_article('SSI lợi nhuận quý III - CafeF'))
        self.assertEqual(get.call_args_list[1].args[0], recent)

    @patch('news_publishers.requests.get')
    def test_exchange_disclosure_checks_article_meta_title(self, get):
        title = 'SSI: Thay đổi giấy đăng ký doanh nghiệp'
        get.side_effect = [response(f'<a href="/notice.chn">{title}</a>'),
                           response(f'<h1>SSI company profile</h1><meta property="og:title" content="{title}">')]
        self.assertEqual(disclosure_article(title + ' - Vietstock')[0], 'https://cafef.vn/story.chn')

    @patch('news_publishers.requests.get')
    def test_transient_catalog_failure_is_not_cached(self, get):
        get.side_effect = [requests.Timeout(), response('<urlset/>')]
        with self.assertRaises(requests.Timeout):
            _sitemap('https://cafef.vn/sitemap.xml', 1)
        self.assertEqual(_sitemap('https://cafef.vn/sitemap.xml', 1), (False, []))


if __name__ == '__main__':
    unittest.main()
