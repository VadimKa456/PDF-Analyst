"""Validation for user-configured OpenAI-compatible and Ollama endpoints."""
from __future__ import annotations

import ipaddress
import re
from urllib.parse import urlsplit


_LOCAL_HOSTS = {"localhost"}
_BLOCKED_LOCAL_SUFFIXES = (
    ".localhost",
    ".local",
    ".internal",
    ".lan",
    ".home.arpa",
)


def validate_ai_base_url(value: str, *, setting_name: str = "AI endpoint") -> str:
    """Validate an AI endpoint before sending document facts or credentials to it.

    Remote providers must use HTTPS. Plain HTTP is permitted only for loopback
    endpoints (the default local Ollama setup). Private/reserved IP literals,
    URL credentials, query strings, fragments and local-only DNS suffixes are
    rejected. Hostnames for public HTTPS providers remain user-configurable.
    """
    raw = str(value or "").strip()
    if not raw:
        raise ValueError(f"{setting_name}: URL не задан.")

    if any(ord(char) < 32 or ord(char) == 127 for char in raw) or "\\" in raw:
        raise ValueError(f"{setting_name}: URL содержит недопустимые символы.")

    try:
        parsed = urlsplit(raw)
        hostname = parsed.hostname
        port = parsed.port
    except ValueError:
        raise ValueError(f"{setting_name}: некорректный URL или порт.") from None

    scheme = parsed.scheme.lower()
    if scheme not in {"http", "https"}:
        raise ValueError(f"{setting_name}: разрешены только схемы HTTPS и HTTP для localhost.")
    if not hostname:
        raise ValueError(f"{setting_name}: в URL должен быть указан адрес сервера.")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError(f"{setting_name}: логин и пароль нельзя помещать в URL.")
    if parsed.query or parsed.fragment:
        raise ValueError(f"{setting_name}: query и fragment в базовом URL не поддерживаются.")

    host = hostname.rstrip(".").lower()
    if not host:
        raise ValueError(f"{setting_name}: некорректное имя сервера.")

    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None

    is_loopback = host in _LOCAL_HOSTS or bool(address and address.is_loopback)
    if address is not None and not (address.is_global or address.is_loopback):
        raise ValueError(
            f"{setting_name}: частные, служебные и зарезервированные IP-адреса запрещены; "
            "для локального сервиса используйте localhost."
        )

    if address is None:
        try:
            ascii_host = host.encode("idna").decode("ascii")
        except UnicodeError:
            raise ValueError(f"{setting_name}: некорректное имя сервера.") from None
        label = r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
        if len(ascii_host) > 253 or not re.fullmatch(
            rf"{label}(?:\.{label})*", ascii_host
        ):
            raise ValueError(f"{setting_name}: некорректное имя сервера.")
        if any(host.endswith(suffix) for suffix in _BLOCKED_LOCAL_SUFFIXES):
            raise ValueError(
                f"{setting_name}: локальные DNS-имена не поддерживаются; "
                "используйте localhost или доверенный HTTPS-адрес."
            )

    if scheme == "http" and not is_loopback:
        raise ValueError(
            f"{setting_name}: удалённые AI-провайдеры должны использовать HTTPS; "
            "HTTP разрешён только для localhost."
        )

    # Accessing parsed.port above validates the numeric range.
    if port == 0:
        raise ValueError(f"{setting_name}: порт 0 не является допустимым адресом сервера.")
    # Keep the original path (some compatible providers host their API below a prefix).
    return raw.rstrip("/")
