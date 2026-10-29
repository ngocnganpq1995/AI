import unittest
from unittest.mock import Mock, patch

import requests

from news_fetch import (ArticleUnavailable, read_source_article, resolve_source_url,
                        publisher_feed_url, publisher_index_url, publisher_permalink_article)


GOOGLE_URL = "https://news.google.com/rss/articles/test-article?oc=5"
PUBLISHER_URL = "https://example.com/tin-doanh-nghiep.html"
TITLE = "Doanh nghiệp công bố kế hoạch phát hành cổ phiếu thưởng"
ARTICLE = (
    "Doanh nghiệp công bố kế hoạch phát hành cổ phiếu thưởng cho cổ đông hiện hữu. "
    "Ngày đăng ký cuối cùng dự kiến là 20/09/2026 với tỷ lệ thực hiện 10:1. "
    "Doanh nghiệp dự kiến phát hành 171 triệu cổ phiếu từ nguồn lợi nhuận chưa phân phối."
)


def response_with(content, status=200):
    response = Mock()
    response.status_code = status
    response.content = content
    response.url = PUBLISHER_URL
    response.raise_for_status.return_value = None
    if status >= 400:
        response.raise_for_status.side_effect = requests.HTTPError(f"HTTP {status}")
    return response


class NewsFetchTests(unittest.TestCase):
    @patch('news_fetch.gnewsdecoder')
    @patch('news_fetch.requests.get')
    def test_vietnam_publisher_article_bypasses_google_429(self, get, decoder):
        title = 'VCBS dự báo lợi nhuận quý III/2026 của SSI, HCM và VCI giảm'
        full_article = ARTICLE + ' ' + ARTICLE
        document = (f'<h1>{title}</h1><div class="post-detail-body"><p>{full_article}</p></div>')
        response = response_with(document.encode('utf-8'))
        response.url = 'https://www.vietnam.vn/vcbs-du-bao-loi-nhuan-quy-iii-2026-cua-ssi-hcm-va-vci-giam'
        get.return_value = response

        self.assertEqual(read_source_article(GOOGLE_URL, title + ' - Vietnam.vn'), full_article)
        decoder.assert_not_called()
        self.assertEqual(get.call_args.args[0], response.url)

    @patch('news_fetch.requests.get')
    def test_vietnam_permalink_rejects_unrelated_headline(self, get):
        response = response_with(f'<h1>Tin khác</h1><p>{ARTICLE * 3}</p>'.encode('utf-8'))
        response.url = 'https://www.vietnam.vn/tin-khac'
        get.return_value = response
        self.assertIsNone(publisher_permalink_article('SSI công bố lợi nhuận - Vietnam.vn'))

    @patch('news_fetch.gnewsdecoder')
    @patch('news_fetch.requests.get')
    def test_exact_publisher_match_reads_article_without_google(self, get, decoder):
        title = 'Triển vọng tăng trưởng của ngân hàng VCB'
        full_article = ARTICLE + ' ' + ARTICLE
        get.side_effect = [response_with(f'<a href="/vcb">{title}</a>'.encode()),
                           response_with(f'<div class="article-body"><p>{full_article}</p></div>'.encode())]
        result = read_source_article(GOOGLE_URL, title + ' - kinhtechungkhoan.vn')
        self.assertEqual(result, full_article)
        decoder.assert_not_called()

    @patch('news_fetch.publisher_index_url', return_value='https://example.com/teaser')
    @patch('news_fetch.resolve_source_url', return_value=PUBLISHER_URL)
    @patch('news_fetch.requests.get')
    def test_short_archive_result_retries_original_article(self, get, resolve, index):
        get.side_effect = [response_with(b'<meta name="description" content="Doanh nghiep teaser">'),
                           response_with(f'<article><p>{ARTICLE}</p></article>'.encode())]
        self.assertEqual(read_source_article(GOOGLE_URL, TITLE), ARTICLE)
        self.assertEqual(get.call_count, 2)

    @patch('news_fetch.publisher_index_url', return_value=PUBLISHER_URL)
    @patch('news_fetch.resolve_source_url', side_effect=ArticleUnavailable('offline'))
    @patch('news_fetch.requests.get')
    def test_google_failure_keeps_usable_short_article(self, get, resolve, index):
        get.return_value = response_with(f'<article><p>{ARTICLE}</p></article>'.encode())
        self.assertEqual(read_source_article(GOOGLE_URL, TITLE), ARTICLE)

    @patch('news_fetch.requests.get')
    def test_publisher_match_rejects_other_domain_and_similar_title(self, get):
        get.return_value = response_with(b'<a href="https://other.com/story">Expected headline</a><a href="/story">Similar headline</a>')
        self.assertIsNone(publisher_index_url('Expected headline - kinhtechungkhoan.vn'))

    @patch('news_fetch.requests.get')
    def test_publisher_page_resolves_exact_headline_when_feed_lags(self, get):
        title = 'Con gái Chủ tịch PNJ bán thành công 18 triệu cổ phiếu'
        link = '/con-gai-chu-tich-pnj-ban-thanh-cong-18-trieu-co-phieu.htm'
        get.side_effect = [response_with(b'<rss><channel></channel></rss>'),
                           response_with(f'<a href="{link}">{title}</a>'.encode('utf-8'))]
        self.assertEqual(publisher_feed_url(title + ' - VnEconomy'), 'https://vneconomy.vn' + link)

    @patch('news_fetch.requests.get')
    def test_similar_headline_is_not_substituted(self, get):
        get.return_value = response_with(b'<a href="/other.htm">Different news headline</a>')
        self.assertIsNone(publisher_feed_url('Exact expected headline - VnEconomy'))

    @patch("news_fetch.gnewsdecoder")
    def test_direct_publisher_url_skips_google_decoder(self, decoder):
        self.assertEqual(resolve_source_url(PUBLISHER_URL), PUBLISHER_URL)
        decoder.assert_not_called()

    @patch("news_fetch.gnewsdecoder")
    def test_google_url_resolves_to_publisher(self, decoder):
        decoder.return_value = {"status": True, "decoded_url": PUBLISHER_URL}
        self.assertEqual(resolve_source_url(GOOGLE_URL), PUBLISHER_URL)
        decoder.assert_called_once_with(GOOGLE_URL, interval=1)

    @patch("news_fetch.gnewsdecoder")
    def test_failed_or_unresolved_google_url_raises(self, decoder):
        failures = [
            {"status": False, "message": "Could not decode"},
            {"status": True, "decoded_url": GOOGLE_URL},
            {"status": True, "decoded_url": ""},
            {"status": True, "decoded_url": "javascript:alert(1)"},
        ]
        for result in failures:
            with self.subTest(result=result):
                decoder.return_value = result
                with self.assertRaises(ArticleUnavailable):
                    resolve_source_url(GOOGLE_URL)

    @patch("news_fetch.gnewsdecoder", side_effect=requests.Timeout("decode timed out"))
    def test_decoder_exception_raises_article_unavailable(self, decoder):
        with self.assertRaises(ArticleUnavailable):
            resolve_source_url(GOOGLE_URL)

    @patch("news_fetch.requests.get")
    def test_request_failures_raise_article_unavailable(self, get):
        for error in (requests.Timeout("timed out"), requests.ConnectionError("offline")):
            with self.subTest(error=type(error).__name__):
                get.side_effect = error
                with self.assertRaises(ArticleUnavailable):
                    read_source_article(PUBLISHER_URL, TITLE)

    @patch("news_fetch.requests.get")
    def test_http_error_is_not_returned_as_article(self, get):
        get.return_value = response_with(b"Access denied", status=403)
        with self.assertRaises(ArticleUnavailable):
            read_source_article(PUBLISHER_URL, TITLE)

    @patch("news_fetch.extract_article", return_value="")
    @patch("news_fetch.requests.get")
    def test_empty_extraction_raises_article_unavailable(self, get, extract):
        get.return_value = response_with(b"<html>Nothing to extract</html>")
        with self.assertRaises(ArticleUnavailable):
            read_source_article(PUBLISHER_URL, TITLE)

    @patch("news_fetch.extract_article", return_value=ARTICLE)
    @patch("news_fetch.requests.get")
    @patch("news_fetch.resolve_source_url", return_value=PUBLISHER_URL)
    def test_fetch_passes_original_bytes_and_title_to_extractor(self, resolve, get, extract):
        document = f'<meta charset="utf-8"><article><p>{ARTICLE}</p></article>'.encode("utf-8")
        get.return_value = response_with(document)
        self.assertEqual(read_source_article(GOOGLE_URL, TITLE), ARTICLE)
        resolve.assert_called_once_with(GOOGLE_URL)
        self.assertEqual(get.call_args.args[0], PUBLISHER_URL)
        self.assertEqual(get.call_args.kwargs["timeout"], (5, 15))
        extract.assert_called_once_with(document, title=TITLE)

    @patch("news_fetch.requests.get")
    def test_vietnamese_article_text_is_returned_without_mojibake(self, get):
        document = f'<meta charset="utf-8"><article><p>{ARTICLE}</p></article>'.encode("utf-8")
        get.return_value = response_with(document)
        self.assertEqual(read_source_article(PUBLISHER_URL, TITLE), ARTICLE)


if __name__ == "__main__":
    unittest.main()
