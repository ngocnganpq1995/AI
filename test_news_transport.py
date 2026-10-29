"""Offline regressions for startup's formerly missing article loader."""
import base64
import json
import unittest
from unittest.mock import patch

import requests

from news_transport import ArticleUnavailable, read_source_article
from news_content import extract_article


ARTICLE = ("Doanh nghiệp công bố doanh thu tăng 20% so với cùng kỳ năm trước. "
           "Lợi nhuận sau thuế đạt 500 tỷ đồng, nhờ hoạt động kinh doanh cốt lõi. "
           "Công ty dự kiến chia cổ tức vào tháng tới và tiếp tục đầu tư mở rộng sản xuất.")
DOCUMENT = ('<meta charset="utf-8"><article class="article-body"><p>' + ARTICLE + '</p></article>').encode()


class ArticleLoaderTests(unittest.TestCase):
    def test_publisher_body_wins_over_unrelated_article_cards(self):
        other = 'Thị trường vàng và chuyến thăm chính thức được cập nhật trong ngày. ' * 10
        for wrapper in ('<main class="article-editor">', '<div class="mekong-detail-body">'):
            end = '</main>' if wrapper.startswith('<main') else '</div>'
            page = f'{wrapper}<p>{ARTICLE}</p>{end}<article><p>{other}</p></article>'
            self.assertEqual(extract_article(page, 'Doanh nghiệp công bố doanh thu và cổ tức'), ARTICLE)

    def test_unrelated_cards_do_not_become_source_text(self):
        page = '<article><p>' + ('Tin về chính trị quốc tế, nội dung không liên quan. ' * 10) + '</p></article>'
        self.assertEqual(extract_article(page, 'FPT phát hành cổ phiếu thưởng'), '')

    @patch("news_transport._request", return_value=("https://publisher.test/news", DOCUMENT))
    def test_direct_article_preserves_vietnamese(self, request):
        self.assertEqual(read_source_article("https://publisher.test/news"), ARTICLE)

    @patch("news_transport._request")
    def test_modern_google_link_resolves_before_extraction(self, request):
        payload = json.dumps([["wrb.fr", "Fbv4je", json.dumps(["garturlres", "https://publisher.test/news"])]])
        request.side_effect = [
            ("https://news.google.com/articles/CBMiabc", b'<div data-n-a-sg="sig" data-n-a-ts="123"></div>'),
            ("https://news.google.com/_/DotsSplashUi/data/batchexecute", ("')]}'\n\n100\n" + payload).encode()),
            ("https://publisher.test/news", DOCUMENT),
        ]
        self.assertEqual(read_source_article("https://news.google.com/rss/articles/CBMiabc"), ARTICLE)
        self.assertEqual(request.call_args_list[-1].args[2], "https://publisher.test/news")

    @patch("news_transport._request", return_value=("https://publisher.test/news", DOCUMENT))
    def test_legacy_google_link(self, request):
        token = base64.urlsafe_b64encode(b'\x08\x13\x22https://publisher.test/news\xd2\x01\x00').decode().rstrip("=")
        self.assertEqual(read_source_article("https://news.google.com/rss/articles/" + token), ARTICLE)
        request.assert_called_once()

    @patch("news_transport._request", side_effect=requests.Timeout)
    def test_network_failure_is_retryable(self, request):
        for _ in range(2):
            with self.assertRaises(ArticleUnavailable):
                read_source_article("https://publisher.test/news")
        self.assertEqual(request.call_count, 2)

    @patch("news_transport._request")
    def test_google_consent_and_empty_articles_are_not_summaries(self, request):
        for final_url, document in [("https://consent.google.com/", DOCUMENT),
                                    ("https://publisher.test/news", b"<p>Sign in</p>")]:
            request.return_value = (final_url, document)
            with self.assertRaises(ArticleUnavailable):
                read_source_article("https://publisher.test/news")

    @patch("news_transport.requests.Session")
    def test_requests_have_timeouts_and_responses_close(self, factory):
        session = factory.return_value.__enter__.return_value
        response = session.request.return_value.__enter__.return_value
        response.url = "https://publisher.test/news"
        response.iter_content.return_value = [DOCUMENT]
        self.assertEqual(read_source_article(response.url), ARTICLE)
        self.assertEqual(session.request.call_args.kwargs["timeout"], (5, 12))
        self.assertTrue(session.request.call_args.kwargs["stream"])
        session.request.return_value.__exit__.assert_called_once()

    def test_non_web_urls_are_rejected(self):
        with self.assertRaises(ArticleUnavailable):
            read_source_article("file:///etc/passwd")


if __name__ == "__main__":
    unittest.main()
