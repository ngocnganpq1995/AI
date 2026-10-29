import unittest
import os
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import streamlit as st
from streamlit.testing.v1 import AppTest

from news_fetch import ArticleUnavailable
from equity_fixture import make_bundle


APP_PATH = Path(__file__).resolve().parents[1] / "app.py"
ARTICLE = (
    "Doanh nghiệp công bố kế hoạch phát hành cổ phiếu thưởng cho cổ đông hiện hữu. "
    "Ngày đăng ký cuối cùng dự kiến là 20/09/2026 với tỷ lệ thực hiện 10:1. "
    "Doanh nghiệp dự kiến phát hành 171 triệu cổ phiếu từ nguồn lợi nhuận chưa phân phối. "
    "Việc phát hành nhằm tăng vốn điều lệ và hỗ trợ kế hoạch đầu tư dài hạn. "
    "Trong sáu tháng đầu năm, doanh thu tăng 15% so với cùng kỳ năm trước."
)


class NewsAppTests(unittest.TestCase):
    def setUp(self):
        st.cache_data.clear()

    def tearDown(self):
        st.cache_data.clear()

    def test_gemini_controls_remain_usable_without_configured_keys(self):
        app = AppTest.from_file(str(APP_PATH), default_timeout=30)
        with patch("equity_views.load_equity", side_effect=make_bundle):
            app.run()
            app.toggle(key="news_ai").set_value(True).run()
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(app.selectbox(key="news_key_label").value, "Chưa có API key")
        self.assertEqual(app.multiselect(key="news_models").value, ["gemini-3.5-flash-lite"])

    def test_gemini_settings_can_be_prepared_before_turning_ai_on(self):
        app = AppTest.from_file(str(APP_PATH), default_timeout=30)
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}), \
             patch("gemini_runtime.list_text_models", return_value=("gemini-3.5-flash-lite", "gemini-3.8-flash")), \
             patch("equity_views.load_equity", side_effect=make_bundle):
            app.run()
            self.assertFalse(app.toggle(key="news_ai").value)
            self.assertFalse(app.selectbox(key="news_key_label").disabled)
            self.assertFalse(app.multiselect(key="news_models").disabled)
            self.assertFalse(app.toggle(key="news_auto_switch").disabled)
            app.multiselect(key="news_models").set_value(["gemini-3.5-flash-lite", "gemini-3.8-flash"]).run()
            app.toggle(key="news_auto_switch").set_value(True).run()
        self.assertEqual(len(app.exception), 0)
        self.assertFalse(app.toggle(key="news_ai").value)
        self.assertTrue(app.toggle(key="news_auto_switch").value)

    def test_gemini_controls_allow_multiple_models_and_auto_switch(self):
        app = AppTest.from_file(str(APP_PATH), default_timeout=30)
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}), \
             patch("gemini_runtime.list_text_models", return_value=("gemini-2.5-flash", "gemini-2.5-pro")), \
             patch("equity_views.load_equity", side_effect=make_bundle):
            app.run()
            app.toggle(key="news_ai").set_value(True).run()
            app.multiselect(key="news_models").set_value(["gemini-2.5-flash", "gemini-2.5-pro"]).run()
            app.toggle(key="news_auto_switch").set_value(True).run()
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(app.selectbox(key="news_key_label").value, "Key cục bộ")
        self.assertEqual(app.multiselect(key="news_models").value, ["gemini-2.5-flash", "gemini-2.5-pro"])
        self.assertTrue(app.toggle(key="news_auto_switch").value)

    def test_retry_recovers_after_failed_read_without_caching_the_failure(self):
        item = {
            "ticker": "FPT",
            "tickers": {"FPT"},
            "title": "Doanh nghiệp công bố kế hoạch phát hành cổ phiếu thưởng",
            "source": "Nguồn kiểm thử",
            "published": "11/09/2026 09:00",
            "date": "11/09/2026",
            "published_dt": datetime(2026, 9, 11, 2, tzinfo=timezone.utc),
            "summary": "Doanh nghiệp công bố kế hoạch phát hành cổ phiếu thưởng.",
            "url": "https://example.com/cache-retry-regression.html",
            "article_text": "",
            "bond_info": "-",
        }
        app = AppTest.from_file(str(APP_PATH), default_timeout=30)
        app.session_state["merged_news"] = [item]

        with patch("equity_views.load_equity", side_effect=make_bundle), patch("news_fetch.read_source_article", side_effect=[ArticleUnavailable("offline"), ARTICLE]) as read:
            app.run()
            self.assertEqual(len(app.exception), 0)
            read.assert_not_called()

            app.button(key="retry_missing_articles").click().run()
            self.assertEqual(len(app.exception), 0)
            self.assertEqual(read.call_count, 1)
            self.assertEqual(app.session_state["merged_news"][0]["article_text"], "")
            self.assertIn("retry_missing_articles", [button.key for button in app.button])

            app.button(key="retry_missing_articles").click().run()
            self.assertEqual(len(app.exception), 0)
            self.assertEqual(read.call_count, 2, "The failed read must be retried instead of cached.")
            self.assertEqual(app.session_state["merged_news"][0]["article_text"], ARTICLE)
            self.assertNotIn("retry_missing_articles", [button.key for button in app.button])
            self.assertTrue(any("171 triệu" in element.value for element in app.markdown))
            paragraphs = [element.value for element in app.markdown if 'class="article-summary"' in element.value]
            self.assertEqual(len(paragraphs), 1)
            self.assertGreaterEqual(paragraphs[0].count('<li>'), 4)
            self.assertLessEqual(paragraphs[0].count('<li>'), 8)
            self.assertNotIn('\n', paragraphs[0])
            self.assertFalse(any('Góc nhìn nhanh:' in element.value for element in app.markdown))


if __name__ == "__main__":
    unittest.main()
