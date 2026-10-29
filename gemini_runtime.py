"""Gemini model discovery and text generation."""

from dataclasses import dataclass
import re

import requests


DEFAULT_MODELS = ("gemini-3.5-flash-lite", "gemini-3.5-flash", "gemini-3.8-flash")
RECOVERABLE_STATUSES = {400, 404, 408, 429, 500, 502, 503, 504}


def list_text_models(api_key):
    """List the key's models that support generateContent."""
    models = []
    page_token = None
    while True:
        params = {"pageSize": 1000}
        if page_token:
            params["pageToken"] = page_token
        response = requests.get(
            "https://generativelanguage.googleapis.com/v1beta/models",
            headers={"x-goog-api-key": api_key},
            params=params,
            timeout=(5, 20),
        )
        response.raise_for_status()
        payload = response.json()
        for entry in payload.get("models", []):
            name = entry.get("name", "")
            non_text = ("image", "audio", "tts", "live", "embedding")
            if (name.startswith("models/gemini-")
                    and not any(kind in name.lower() for kind in non_text)
                    and "generateContent" in entry.get("supportedGenerationMethods", [])):
                models.append(name.removeprefix("models/"))
        page_token = payload.get("nextPageToken")
        if not page_token:
            break
    return tuple(dict.fromkeys(models))


def generate_with_fallback(api_key, models, instructions, content, auto_switch=False, pdf_data=None, image_data=None):
    """Try selected models in order; only temporary/model errors trigger fallback."""
    choices = tuple(models if auto_switch else models[:1])
    if not api_key or not choices:
        return GeminiResult(None, None, "Chưa chọn API key và mô hình Gemini.")

    body = {
        "systemInstruction": {"parts": [{"text": instructions}]},
        "contents": [{"role": "user", "parts": [{"text": content}]}],
    }
    if pdf_data:
        import base64
        body['contents'][0]['parts'].append({'inlineData': {
            'mimeType': 'application/pdf', 'data': base64.b64encode(pdf_data).decode('ascii')}})
    if image_data:
        import base64
        for mime, data in image_data:
            body['contents'][0]['parts'].append({'inlineData': {
                'mimeType': mime, 'data': base64.b64encode(data).decode('ascii')}})
    for index, model in enumerate(choices):
        if not re.fullmatch(r"gemini-[A-Za-z0-9_.-]+", model):
            return GeminiResult(None, None, "Tên mô hình Gemini không hợp lệ.")
        try:
            response = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                headers={"x-goog-api-key": api_key},
                json=body,
                timeout=(5, 90),
            )
        except requests.RequestException:
            if index + 1 < len(choices):
                continue
            return GeminiResult(None, None, "Không kết nối được Gemini. Hãy thử quét lại.")

        if response.status_code != 200:
            if response.status_code in RECOVERABLE_STATUSES and index + 1 < len(choices):
                continue
            if response.status_code in {401, 403}:
                return GeminiResult(None, None, "Gemini API key không hợp lệ, hết hiệu lực hoặc không có quyền. Hãy nhập API key khác.")
            return GeminiResult(None, None, f"Gemini chưa xử lý được yêu cầu (HTTP {response.status_code}).")

        try:
            candidate = response.json().get("candidates", [{}])[0]
            if candidate.get("finishReason") == "SAFETY":
                return GeminiResult(None, None, "Gemini không thể xử lý nội dung bài viết này.")
            parts = candidate.get("content", {}).get("parts", [])
            text = "\n".join(part.get("text", "") for part in parts if part.get("text")).strip()
        except (ValueError, IndexError, AttributeError, TypeError):
            text = ""
        if text:
            return GeminiResult(text, model, None)
        if index + 1 == len(choices):
            return GeminiResult(None, None, "Gemini không trả về nội dung tóm tắt.")

    return GeminiResult(None, None, "Các mô hình đã chọn đều chưa xử lý được bài viết.")
