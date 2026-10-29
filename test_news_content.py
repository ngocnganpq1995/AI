import json
import unittest

from news_content import extract_article, news_table, summary_bullets, summary_paragraph, summary_sentences


ARTICLE = (
    "Công ty công bố kế hoạch phát hành cổ phiếu thưởng cho cổ đông hiện hữu. "
    "Ngày đăng ký cuối cùng dự kiến là 20/09/2026 với tỷ lệ thực hiện 10:1. "
    "Doanh nghiệp dự kiến phát hành 171 triệu cổ phiếu từ nguồn lợi nhuận chưa phân phối. "
    "Việc phát hành nhằm tăng vốn điều lệ và hỗ trợ kế hoạch đầu tư dài hạn. "
    "Trong sáu tháng đầu năm, doanh thu tăng 15% so với cùng kỳ năm trước. "
    "Ban lãnh đạo cho biết tiến độ còn phụ thuộc vào phê duyệt của cơ quan quản lý. "
    "Công ty công bố kế hoạch phát hành cổ phiếu thưởng cho cổ đông hiện hữu."
)


class NewsContentTests(unittest.TestCase):
    def test_bullets_keep_four_to_eight_distinct_facts(self):
        points = summary_bullets({"title": "Tiêu đề", "article_text": ARTICLE})
        self.assertGreaterEqual(len(points), 4)
        self.assertLessEqual(len(points), 8)
        self.assertEqual(len(points), len(set(points)))
        self.assertIn("171 triệu", " ".join(points))
        many = " ".join(f"Doanh nghiệp số {i} ghi nhận doanh thu {i * 100} tỷ đồng trong kỳ báo cáo." for i in range(15))
        self.assertEqual(len(summary_bullets({"article_text": many})), 8)

    def test_bullets_do_not_pad_sparse_source(self):
        self.assertEqual(summary_bullets({"title": "Chỉ có tiêu đề"}), [])
        point = "Doanh nghiệp dự kiến phát hành 171 triệu cổ phiếu từ lợi nhuận chưa phân phối."
        self.assertEqual(summary_bullets({"article_text": point}), [point])

    def test_title_is_fallback_when_source_has_no_summary(self):
        item = {"title": "Cổ phiếu PNJ tăng mạnh - Nguồn báo", "summary": ""}
        self.assertEqual(summary_paragraph(item), "Cổ phiếu PNJ tăng mạnh")

    def test_short_ai_summary_is_not_expanded_to_meet_a_minimum(self):
        points = summary_bullets({"article_text": ARTICLE}, ai_text="Doanh nghiệp công bố kế hoạch phát hành cổ phiếu thưởng cho cổ đông hiện hữu.")
        self.assertEqual(len(points), 1)

    def test_promotional_text_is_removed_from_cached_and_ai_summaries(self):
        fact = "Techcombank dự kiến chia cổ tức bằng cổ phiếu với tỷ lệ 50% trong năm 2026."
        noise = ["Bấm vào mỗi từ khóa để xem bài cùng chủ đề", "#Ngân hàng TMCP Kỹ thương Việt Nam",
                 "Kết nối truyền thông cùng 24HMONEY ?", "Cài đặt tiện ích 24HMoney extension",
                 "để theo dõi thị trường và mã chứng khoán mọi nơi trên trình duyệt Chrome",
                 "Xem HDSD để tận dụng tối đa tiện ích"]
        text = '\n'.join([fact] + noise)
        self.assertEqual(summary_bullets({'article_text': text}), [fact])
        self.assertEqual(summary_bullets({'article_text': ARTICLE}, ai_text=text), [fact])
        self.assertEqual(summary_bullets({'article_text': '\n'.join(noise)}), [])

    def test_inner_article_body_excludes_outer_promotions(self):
        document = ('<div class="article-detail-content"><div class="news-content"><p>' + ARTICLE +
                    '</p></div><p>Hướng dẫn sử dụng các tính năng của nền tảng dành cho bạn đọc.</p>'
                    '<p>Cài đặt tiện ích 24HMoney extension trên trình duyệt của bạn.</p></div>')
        self.assertEqual(extract_article(document), ARTICLE)

    def test_detail_is_longer_and_retains_conditions_without_inventing_facts(self):
        sentences = [
            f"Mảng hoạt động số {i} ghi nhận doanh thu {i * 100} tỷ đồng trong quý này, "
            "tăng so với cùng kỳ nhờ đơn hàng mới từ khách hàng hiện hữu và tiến độ bàn giao tốt hơn."
            for i in range(1, 10)
        ] + ["Tuy nhiên, kế hoạch còn phụ thuộc vào phê duyệt của cơ quan quản lý và tiến độ giải ngân trong quý tiếp theo."]
        item = {"title": "Kết quả kinh doanh", "article_text": " ".join(sentences)}
        detail = summary_sentences(item, detail=True)
        self.assertGreater(len(" ".join(detail).split()), 250)
        self.assertLessEqual(len(" ".join(detail).split()), 400)
        self.assertGreater(len(detail), len(summary_sentences(item)))
        self.assertIn(sentences[-1], detail)
        self.assertTrue(all(sentence in sentences for sentence in detail))

    def test_paragraph_is_short_single_block_and_keeps_numbers(self):
        item = {"title": "Tiêu đề", "article_text": ARTICLE}
        paragraph = summary_paragraph(item)
        self.assertNotIn("\n", paragraph)
        self.assertLessEqual(len(paragraph.split()), 140)
        self.assertIn("171 triệu", paragraph)
        self.assertNotIn("**", paragraph)

    def test_title_only_rss_is_not_presented_as_summary(self):
        title = "FPT phát hành cổ phiếu thưởng cho cổ đông hiện hữu"
        for text in (title, title + " - Nguồn báo", "<a>" + title + "</a> - Nguồn báo"):
            item = {"title": title + " - Nguồn báo", "summary": text}
            self.assertEqual(summary_paragraph(item), title)

    def test_ai_multiline_text_is_presented_as_one_paragraph(self):
        result = summary_paragraph({"title": "Tiêu đề"}, ai_text="- " + ARTICLE.replace(". ", ".\n- "))
        self.assertNotIn("\n", result)
        self.assertNotIn("- ", result)
        self.assertLessEqual(len(result.split()), 140)

    def test_div_paragraphs_are_not_lost_when_teaser_uses_p(self):
        document = ('<div class="article-detail-content"><p>Mô tả ngắn của bài báo về phát hành cổ phiếu.</p>'
                    '<div class="news-content"><div class="paragraph">' + ARTICLE + '</div></div></div>')
        self.assertIn(ARTICLE, extract_article(document))

    def test_lists_tables_and_more_complete_body_are_preserved(self):
        document = ('<div class="entry-body"><p>' + ARTICLE[:200] + '</p></div>'
                    '<div class="article-body"><p>' + ARTICLE + '</p>'
                    '<ul><li><p>Ngày thực hiện dự kiến: 30/09/2026.</p></li></ul>'
                    '<table><tr><th>Lợi nhuận sau thuế</th><td>1.250 tỷ đồng</td></tr></table></div>')
        result = extract_article(document)
        self.assertIn(ARTICLE, result)
        self.assertEqual(result.count('Ngày thực hiện dự kiến'), 1)
        self.assertIn('Lợi nhuận sau thuế 1.250 tỷ đồng', result)

    def test_full_publisher_body_wins_over_short_structured_description(self):
        for container in ('<div id="content_detail_news">', '<div class="entry-body">',
                          '<div class="article-detail-content">', '<div class="post-detail-body"><div class="ql-editor">'):
            with self.subTest(container=container):
                document = ('<script type="application/ld+json">' + json.dumps({'articleBody': 'Mô tả ngắn'})
                            + '</script>' + container + '<p>' + ARTICLE + '</p></div></div>')
                self.assertEqual(extract_article(document), ARTICLE)

    def test_summary_keeps_context_facts_order_and_no_duplicates(self):
        item = {"title": "Tiêu đề", "article_text": ARTICLE}
        overview = summary_sentences(item)
        detail = summary_sentences(item, detail=True)
        self.assertEqual(len(overview), 4)
        self.assertEqual(len(detail), 6)
        self.assertTrue(overview[0].startswith("Công ty"))
        self.assertIn("171 triệu", " ".join(detail))
        self.assertIn("phê duyệt", " ".join(detail))
        self.assertLessEqual(len(" ".join(detail).split()), 220)
        self.assertEqual(len(detail), len(set(detail)))

    def test_sparse_source_is_not_padded(self):
        title = "Doanh nghiệp công bố ngày chốt quyền cổ tức"
        self.assertEqual(summary_sentences({"title": title}), [title])

    def test_utf8_bytes_preserve_vietnamese(self):
        document = f'<meta charset="utf-8"><article><p>{ARTICLE}</p></article>'
        self.assertEqual(extract_article(document.encode('utf-8')), ARTICLE)

    def test_unrelated_publisher_description_is_rejected(self):
        document = '<meta property="og:description" content="Chuyến thăm chính thức tại Paris của đoàn đại biểu.">'
        self.assertEqual(extract_article(document, title='FPT phát hành cổ phiếu thưởng'), '')

    def test_structured_article_body_survives_script_removal(self):
        document = '<script type="application/ld+json">' + json.dumps({"@graph": [{"articleBody": ARTICLE}]}) + '</script>'
        self.assertEqual(extract_article(document), ARTICLE)

    def test_article_excludes_unrelated_navigation(self):
        document = f'<nav><p>UNRELATED NAVIGATION</p></nav><article><p>{ARTICLE}</p></article>'
        self.assertEqual(extract_article(document), ARTICLE)
        self.assertEqual(extract_article('<nav><p>Login to read more</p></nav>'), '')

    def test_table_escapes_content_and_has_no_bond_column(self):
        row = {"Ngày": "11/09/2026", "Mã CK": "FPT", "Tóm tắt thông tin": '<script>alert(1)</script>',
               "Tiêu đề bài báo": '<script>alert(1)</script>',
               "Source": "A & B", "Loại tin": "Doanh nghiệp", "Đọc tin gốc": "javascript:alert(1)"}
        result = news_table([row])
        self.assertNotIn('<script>', result)
        self.assertNotIn('href="javascript:', result)
        self.assertNotIn('Trái phiếu', result)
        self.assertIn('&lt;script&gt;', result)


if __name__ == '__main__':
    unittest.main()
