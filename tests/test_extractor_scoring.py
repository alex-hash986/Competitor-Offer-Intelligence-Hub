import socket

import httpx
import pytest
from fastapi import HTTPException

from app.services import extractor
from app.services.scoring import calculate_cro_score

HTML = """
<h1>Автоматизация маркетинга для команды</h1>
<h2>Внедрим решение за 14 дней с поддержкой менеджера</h2>
<p>19 900 ₽, 19900 руб, 45 000 р., 2024 руб, скидка 10%</p>
<button>Оставить заявку</button><a href="/demo">Demo</a>
<p>Кейсы, отзывы, гарантия возврата, 200 клиентов</p>
<p>Бесплатный аудит, триал 14 дней, чек-лист, рассрочка 0%</p>
<script>700 ₽</script>
"""


def test_raw_html_and_maximum_score():
    result = extractor.extract_offer_elements(HTML)
    assert result["extracted_prices"] == [19900, 45000]
    assert result["currency"] == "RUB"
    assert result["cta_buttons"] == ["Оставить заявку", "Demo"]
    assert len(result["content_hash"]) == 64
    score, breakdown = calculate_cro_score(result)
    assert score == 100
    assert set(breakdown.values()) == {20}


def test_empty_page():
    result = extractor.extract_offer_elements("")
    score, breakdown = calculate_cro_score(result)
    assert score == 0
    assert set(breakdown.values()) == {0}
    assert result["min_price"] is None


@pytest.mark.parametrize(("value", "price", "currency"), [
    ("$299", 299, "USD"), ("€150", 150, "EUR"), ("19\u202f900 ₽", 19900, "RUB"),
    ("100,50 руб.", 100.5, "RUB"),
])
def test_manual_text(value, price, currency):
    result = extractor.extract_offer_elements(
        f"Курс автоматизации продаж\nПоддержка ментора\nЦена {value}\nЗаписаться\nПробный урок",
        "manual_text",
    )
    assert result["h1_text"] == "Курс автоматизации продаж"
    assert result["min_price"] == price
    assert result["currency"] == currency
    assert result["cta_buttons"] == ["Записаться"]
    assert result["lead_magnets"] == ["Пробный урок"]


def test_structured_and_wrapped_json():
    first = extractor.extract_offer_elements('{"prices":[299,150,299],"currency":"USD"}', "json_snapshot")
    second = extractor.extract_offer_elements({"currency": "USD", "prices": [150, 299]}, "json_snapshot")
    assert first == second
    assert second["extracted_prices"] == [150, 299]
    assert extractor.extract_offer_elements({"html": HTML}, "json_snapshot") == extractor.extract_offer_elements(HTML)


@pytest.mark.parametrize("data", ['{"prices":[-10]}', '{"prices":["10"]}', '{"prices":[NaN]}', '[]', '{broken'])
def test_invalid_json(data):
    with pytest.raises(HTTPException) as exc:
        extractor.extract_offer_elements(data, "json_snapshot")
    assert exc.value.status_code == 422


def mock_http(monkeypatch, handler):
    def send(_, request):
        return handler(request)

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", send)
    monkeypatch.setattr(socket, "getaddrinfo", lambda host, *args, **kwargs: [
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", (host if host == "127.0.0.1" else "93.184.216.34", 443))
    ])


def test_live_url_redirect(monkeypatch):
    def handler(request):
        assert "Mozilla" in request.headers["User-Agent"]
        assert request.url.host == "93.184.216.34"
        assert request.headers["Host"] == "example.com"
        assert request.extensions["sni_hostname"] == "example.com"
        if request.url.path == "/":
            return httpx.Response(302, headers={"Location": "/offer"})
        return httpx.Response(200, text=HTML)

    mock_http(monkeypatch, handler)
    assert extractor.extract_offer_elements("https://example.com", "live_url")["min_price"] == 19900


def test_live_url_rejects_private_redirect(monkeypatch):
    def handler(request):
        assert request.url.host != "127.0.0.1"
        return httpx.Response(302, headers={"Location": "http://127.0.0.1/"})

    mock_http(monkeypatch, handler)
    with pytest.raises(HTTPException) as exc:
        extractor.extract_offer_elements("https://example.com", "live_url")
    assert exc.value.status_code == 422


@pytest.mark.parametrize("connection_error", [False, True])
def test_live_url_upstream_failure(monkeypatch, connection_error):
    def handler(request):
        if connection_error:
            raise httpx.ConnectTimeout("timed out", request=request)
        return httpx.Response(404)

    mock_http(monkeypatch, handler)
    with pytest.raises(HTTPException) as exc:
        extractor.extract_offer_elements("https://example.com", "live_url")
    assert exc.value.status_code == 502
