import unittest
from unittest.mock import Mock, patch

from gemini_runtime import generate_with_fallback, list_text_models


def response(status, payload=None):
    result = Mock(status_code=status)
    result.json.return_value = payload or {}
    return result


class GeminiRuntimeTests(unittest.TestCase):
    @patch('gemini_runtime.requests.post')
    def test_scanned_disclosure_is_sent_as_pdf_with_text(self, post):
        import base64
        post.return_value = response(200, {'candidates': [{'content': {'parts': [{'text': 'Summary from PDF'}]}}]})
        result = generate_with_fallback('key', ('gemini-test',), 'rules', 'notice', pdf_data=b'%PDF-test', image_data=[('image/jpeg', b'image-test')])
        parts = post.call_args.kwargs['json']['contents'][0]['parts']
        self.assertEqual(parts[0], {'text': 'notice'})
        self.assertEqual(parts[1]['inlineData']['mimeType'], 'application/pdf')
        self.assertEqual(base64.b64decode(parts[1]['inlineData']['data']), b'%PDF-test')
        self.assertEqual(parts[2]['inlineData']['mimeType'], 'image/jpeg')
        self.assertEqual(base64.b64decode(parts[2]['inlineData']['data']), b'image-test')
        self.assertEqual(result.text, 'Summary from PDF')

    @patch("gemini_runtime.requests.get")
    def test_model_list_only_includes_gemini_text_models(self, get):
        get.return_value = response(200, {"models": [
            {"name": "models/gemini-2.5-flash", "supportedGenerationMethods": ["generateContent"]},
            {"name": "models/gemini-embedding-001", "supportedGenerationMethods": ["embedContent"]},
            {"name": "models/other", "supportedGenerationMethods": ["generateContent"]},
        ]})
        self.assertEqual(list_text_models("private-key"), ("gemini-2.5-flash",))
        self.assertEqual(get.call_args.kwargs["headers"], {"x-goog-api-key": "private-key"})

    @patch("gemini_runtime.requests.post")
    def test_quota_error_tries_next_selected_model(self, post):
        post.side_effect = [
            response(429),
            response(200, {"candidates": [{"content": {"parts": [{"text": "Kết quả"}]}}]}),
        ]
        result = generate_with_fallback("private-key", ("gemini-first", "gemini-second"),
                                        "rules", "article", auto_switch=True)
        self.assertEqual(result.text, "Kết quả")
        self.assertEqual(result.model, "gemini-second")
        self.assertEqual(post.call_count, 2)

    @patch("gemini_runtime.requests.post")
    def test_bad_key_does_not_retry_other_model(self, post):
        post.return_value = response(403)
        result = generate_with_fallback("bad-key", ("gemini-first", "gemini-second"),
                                        "rules", "article", auto_switch=True)
        self.assertIsNone(result.text)
        self.assertIn("API key", result.error)
        post.assert_called_once()

    @patch("gemini_runtime.requests.post")
    def test_invalid_model_request_tries_next_model(self, post):
        post.side_effect = [
            response(400),
            response(200, {"candidates": [{"content": {"parts": [{"text": "Tin chính"}]}}]}),
        ]
        result = generate_with_fallback("private-key", ("gemini-first", "gemini-second"),
                                        "rules", "article", auto_switch=True)
        self.assertEqual(result.model, "gemini-second")
        self.assertEqual(post.call_count, 2)

    @patch("gemini_runtime.requests.post")
    def test_safety_block_does_not_retry_other_model(self, post):
        post.return_value = response(200, {"candidates": [{"finishReason": "SAFETY"}]})
        result = generate_with_fallback("private-key", ("gemini-first", "gemini-second"),
                                        "rules", "article", auto_switch=True)
        self.assertIsNone(result.text)
        post.assert_called_once()

    @patch("gemini_runtime.requests.post")
    def test_manual_mode_only_calls_first_model(self, post):
        post.return_value = response(429)
        result = generate_with_fallback("private-key", ("gemini-first", "gemini-second"),
                                        "rules", "article", auto_switch=False)
        self.assertIsNone(result.text)
        post.assert_called_once()


if __name__ == "__main__":
    unittest.main()
