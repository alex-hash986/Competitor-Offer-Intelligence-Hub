import hashlib
import ipaddress
import json
import re
import socket
from collections import Counter
from urllib.parse import urlsplit

import httpx
from bs4 import BeautifulSoup
from fastapi import HTTPException
from pydantic import ValidationError

from app.schemas import StructuredSnapshot

MAX_BYTES = 2_000_000
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36"
NUMBER = r"\d{1,3}(?:[ \u00a0\u202f]\d{3})+(?:[,.]\d{1,2})?|\d+(?:[,.]\d{1,2})?"
MONEY = re.compile(
    rf"(?<![\w.,%])(?:(?P<prefix>[$€])\s*(?P<front>{NUMBER})|"
    rf"(?P<back>{NUMBER})[ \t\u00a0\u202f]*(?P<suffix>₽|руб\.?(?!\w)|р\.(?!\w)))"
    r"(?!\d|[.,]\d)(?![ \t]*%)",
    re.I,
)
CTA = re.compile(
    r"\b(?:оставить\s+заявку|попробовать|получить|рассчитать|записаться|купить|"
    r"начать\s+бесплатно|заказать|demo|request\s+a\s+demo|start\s+free)\b", re.I,
)
TRUST = {
    "Кейсы": r"\bкейс\w*|\bcase studies\b",
    "Отзывы": r"\bотзыв\w*|\btestimonials\b",
    "Гарантия": r"гаранти\w*\s+(?:возврат|трудоустройств|кейс)|вернём деньги",
    "Клиенты и выпускники": r"\d[\d\s]*\+?\s*(?:клиент|выпускник)\w*",
    "Лицензии и сертификаты": r"\b(?:лицензи|сертификат)\w*",
    "Партнёры": r"\bпартн[её]р\w*",
    "Рейтинг": r"\bрейтинг\w*|[45][.,]\d\s*(?:/ ?5|★)",
}
LEADS = {
    "Бесплатный аудит": r"бесплатн\w*\s+аудит|аудит\s+бесплатно",
    "Пробный урок": r"пробн\w*\s+урок",
    "Демо-доступ": r"демо[-\s]доступ|бесплатн\w*\s+демо|\bfree demo\b",
    "Триал": r"\bтриал\b|пробн\w*\s+период|\bfree trial\b",
    "Чек-лист": r"чек[-\s]?лист",
    "Шаблон": r"\bшаблон\w*",
    "Рассрочка 0%": r"рассрочк\w*\s+(?:под\s+)?0\s*%",
    "Бесплатная консультация": r"бесплатн\w*\s+консультаци|консультаци\w*\s+бесплатно",
    "Бесплатный интенсив": r"бесплатн\w*\s+(?:\d+[-–]дневн\w*\s+)?интенсив",
}


def resolve_public_address(request: httpx.Request) -> str:
    try:
        url = urlsplit(str(request.url))
        if url.scheme not in {"https", "http"} or not url.hostname or url.username is not None:
            raise ValueError
        if url.port not in {None, 80, 443}:
            raise ValueError
        records = socket.getaddrinfo(url.hostname, url.port, type=socket.SOCK_STREAM)
        addresses = [ipaddress.ip_address(record[4][0]) for record in records]
        if not addresses or any(not address.is_global or address.is_multicast for address in addresses):
            raise ValueError
        return str(addresses[0])
    except ValueError as exc:
        raise HTTPException(422, "Допустим публичный HTTP(S) URL без учётных данных") from exc
    except OSError as exc:
        raise HTTPException(502, "Не удалось разрешить имя сайта") from exc


class PublicHTTPTransport(httpx.HTTPTransport):
    def handle_request(self, request: httpx.Request) -> httpx.Response:
        address = resolve_public_address(request)
        # Connect to the validated address while retaining the original Host and TLS identity.
        direct_request = httpx.Request(
            request.method,
            request.url.copy_with(host=address),
            headers=request.headers,
            stream=request.stream,
            extensions={**request.extensions, "sni_hostname": request.url.raw_host.decode("ascii")},
        )
        return super().handle_request(direct_request)


def fetch_html(url: str) -> str:
    try:
        with httpx.Client(
            follow_redirects=True,
            timeout=15.0,
            max_redirects=5,
            headers={"User-Agent": USER_AGENT},
            transport=PublicHTTPTransport(
                limits=httpx.Limits(max_keepalive_connections=0),
                trust_env=False,
            ),
            trust_env=False,
        ) as client, client.stream("GET", url) as response:
            response.raise_for_status()
            data = bytearray()
            for chunk in response.iter_bytes(chunk_size=65536):
                data.extend(chunk)
                if len(data) > MAX_BYTES:
                    raise HTTPException(422, "Страница превышает 2 МБ")
            return data.decode(response.encoding or "utf-8", errors="replace")
    except (httpx.InvalidURL, httpx.UnsupportedProtocol) as exc:
        raise HTTPException(422, "Укажите корректный HTTP(S) URL") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(502, "Не удалось загрузить страницу") from exc
    except LookupError as exc:
        raise HTTPException(502, "Неизвестная кодировка страницы") from exc


def unique_text(values):
    unique = {}
    for value in values:
        clean = " ".join(value.split())
        if clean:
            unique.setdefault(clean.casefold(), clean)
    return list(unique.values())


def extract_prices(text):
    prices = {}
    frequency = Counter()
    for match in MONEY.finditer(text):
        number = match["front"] or match["back"]
        amount = float(re.sub(r"\s", "", number).replace(",", "."))
        if not (0 <= amount < float("inf")) or (amount.is_integer() and 2020 <= amount <= 2030):
            continue
        currency = {"$": "USD", "€": "EUR"}.get(match["prefix"], "RUB")
        prices.setdefault(currency, set()).add(amount)
        frequency[currency] += 1
    currency = frequency.most_common(1)[0][0] if frequency else "RUB"
    return sorted(prices.get(currency, set())), currency


def format_result(h1, subheadline, prices, currency, cta, trust, leads):
    h1 = " ".join(h1.split())
    subheadline = " ".join(subheadline.split())
    fields = {
        "h1_text": h1,
        "subheadline": subheadline,
        "extracted_prices": sorted(set(prices)),
        "currency": currency,
        "cta_buttons": unique_text(cta),
        "trust_signals": unique_text(trust),
        "lead_magnets": unique_text(leads),
    }
    canonical = json.dumps(fields, ensure_ascii=False, sort_keys=True, allow_nan=False)
    fields["content_hash"] = hashlib.sha256(canonical.encode()).hexdigest()
    fields["min_price"] = min(prices, default=None)
    fields["max_price"] = max(prices, default=None)
    summary = [value for value in (h1, subheadline) if value]
    if prices:
        summary.append(f"От {min(prices):g} {currency}")
    fields["offer_summary"] = " | ".join(summary)
    return fields


def from_text(content, html):
    if html:
        soup = BeautifulSoup(content, "lxml")
        for node in soup.select("script, style, template, noscript, [hidden]"):
            node.decompose()
        h1_node = soup.find("h1")
        subtitle = soup.select_one(".subheadline, .subtitle, [data-subheadline]")
        if subtitle is None and h1_node:
            subtitle = h1_node.find_next(["h2", "p"])
        h1 = h1_node.get_text(" ", strip=True) if h1_node else ""
        sub = subtitle.get_text(" ", strip=True) if subtitle else ""
        cta = [node.get_text(" ", strip=True) for node in soup.select(
            'button, a.btn, [role="button"]'
        )]
        cta.extend(node.get_text(" ", strip=True) for node in soup.select("a") if CTA.search(
            node.get_text(" ", strip=True)
        ))
        text = " ".join(soup.stripped_strings)
    else:
        lines = [line.strip() for line in content.splitlines() if line.strip()]
        h1 = lines[0] if lines else ""
        sub = lines[1] if len(lines) > 1 else ""
        cta = [line for line in lines if len(line) <= 90 and CTA.search(line)]
        text = " ".join(lines)
    cta.extend(match.group() for match in CTA.finditer(text) if not any(
        match.group().casefold() in label.casefold() for label in cta
    ))
    prices, currency = extract_prices(text)
    trust = [label for label, pattern in TRUST.items() if re.search(pattern, text, re.I)]
    leads = [label for label, pattern in LEADS.items() if re.search(pattern, text, re.I)]
    return format_result(h1, sub, prices, currency, cta, trust, leads)


def extract_offer_elements(content: str, mode: str = "raw_html") -> dict:
    if mode == "live_url":
        return from_text(fetch_html(content), html=True)
    if mode == "json_snapshot":
        try:
            data = (StructuredSnapshot.model_validate_json(content) if isinstance(content, str)
                    else StructuredSnapshot.model_validate(content))
        except ValidationError as exc:
            raise HTTPException(422, "Некорректный JSON-снимок") from exc
        if data.html is not None:
            return from_text(data.html, html=True)
        return format_result(data.h1_text, data.subheadline, data.prices, data.currency,
                             data.cta_buttons, data.trust_signals, data.lead_magnets)
    if mode in {"raw_html", "manual_text"}:
        return from_text(content, html=mode == "raw_html")
    raise HTTPException(422, "Неизвестный режим извлечения")
