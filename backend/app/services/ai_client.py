"""Клиент OpenAI-совместимых API и Ollama.

Ключи никогда не логируются и не возвращаются клиенту в открытом виде.
Вся бизнес-логика (расчёты, сравнения) выполняется на Python; LLM используется
только для планирования запроса и формулировки вывода на основе переданных фактов.
"""
from __future__ import annotations

import logging
import time
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx

from .ai_url import validate_ai_base_url

logger = logging.getLogger(__name__)


class AIError(RuntimeError):
    pass


class AIClient:
    def __init__(self, cfg: dict[str, Any]):
        self.cfg = cfg
        self.provider = (cfg.get("ai_provider") or "none").lower()
        self.timeout = float(cfg.get("ai_timeout_seconds") or 90)

    @property
    def available(self) -> bool:
        if self.provider == "none":
            return False
        if self.provider == "ollama":
            try:
                self._ollama_base_url()
                return True
            except AIError:
                return False
        if self.provider == "openai":
            if not self.cfg.get("openai_api_key"):
                return False
            try:
                self._openai_base_url()
                return True
            except AIError:
                return False
        return False

    def _validated_base_url(self, key: str, default: str, label: str) -> str:
        try:
            return validate_ai_base_url(
                str(self.cfg.get(key) or default),
                setting_name=label,
            )
        except ValueError as exc:
            raise AIError(str(exc)) from exc

    def _openai_base_url(self) -> str:
        return self._validated_base_url(
            "openai_base_url",
            "https://api.openai.com/v1",
            "OpenAI-compatible endpoint",
        )

    def _ollama_base_url(self) -> str:
        return self._validated_base_url(
            "ollama_base_url",
            "http://localhost:11434",
            "Ollama endpoint",
        )

    @property
    def model(self) -> str:
        if self.provider == "ollama":
            return str(self.cfg.get("ollama_model") or "llama3.1")
        return str(self.cfg.get("openai_model") or "gpt-4o-mini")

    @property
    def embedding_model(self) -> str:
        if self.provider == "ollama":
            return str(self.cfg.get("ollama_embedding_model") or "nomic-embed-text")
        return str(self.cfg.get("openai_embedding_model") or "text-embedding-3-small")

    def _openai_url(self, path: str) -> str:
        parsed = urlsplit(self._openai_base_url())
        base_path = parsed.path.rstrip("/")
        if not base_path.endswith("/v1"):
            base_path += "/v1"
        return urlunsplit((parsed.scheme, parsed.netloc, base_path + path, "", ""))

    def _headers(self) -> dict[str, str]:
        h = {"Content-Type": "application/json"}
        key = str(self.cfg.get("openai_api_key") or "")
        if key:
            h["Authorization"] = f"Bearer {key}"
        return h

    def _describe_http_error(self, status: int, text: str) -> str:
        """Понятное описание ошибки без раскрытия ключа."""
        detail = (text or "")[:500]
        message = f"AI API вернул ошибку {status}"
        if detail:
            message += f": {detail}"
        low = detail.lower()
        if status in (401, 403):
            message += " — проверьте API-ключ и права доступа."
        elif status == 404 and ("model" in low or "not found" in low):
            message += (
                f" — модель «{self.model}» недоступна у провайдера. "
                "Нажмите «Список моделей» и выберите доступную модель."
            )
        elif status == 429:
            message += " — превышен лимит запросов, попробуйте позже."
        elif status in (500, 502, 503, 504):
            message += " — провайдер временно недоступен, попробуйте позже или выберите другую модель."
        return message

    @staticmethod
    def _retryable(response: httpx.Response) -> bool:
        if response.status_code in {429, 500, 502, 503, 504}:
            return True
        low = (response.text or "").lower()
        return "temporarily unavailable" in low or "try again shortly" in low

    @staticmethod
    def _retry_delay(response: httpx.Response, attempt: int) -> float:
        try:
            data = response.json()
        except ValueError:
            data = {}
        retry_after = data.get("retry_after_seconds") if isinstance(data, dict) else None
        if isinstance(retry_after, (int, float)) and retry_after >= 0:
            return min(float(retry_after), 5.0)
        return float(attempt + 1)

    def _post_openai(self, path: str, payload: dict[str, Any], retries: int = 2) -> httpx.Response:
        """POST к OpenAI-совместимому API с повтором на временных ошибках."""
        for attempt in range(retries + 1):
            try:
                with httpx.Client(timeout=self.timeout, follow_redirects=False) as client:
                    response = client.post(
                        self._openai_url(path), headers=self._headers(), json=payload
                    )
            except httpx.HTTPError as exc:
                raise AIError(f"Не удалось подключиться к AI API: {exc}") from exc
            if response.status_code < 400:
                return response
            if attempt >= retries or not self._retryable(response):
                raise AIError(self._describe_http_error(response.status_code, response.text))
            logger.info(
                "AI API вернул %s, повтор %s/%s", response.status_code, attempt + 1, retries
            )
            time.sleep(self._retry_delay(response, attempt))
        raise AIError("AI API временно недоступен")

    def _model_not_found(self, error: str) -> bool:
        low = error.lower()
        return "model_not_found" in low or (
            "404" in low and "model" in low
        ) or "selected model is unavailable" in low

    def chat(self, messages: list[dict[str, str]], json_mode: bool = False) -> str:
        if not self.available:
            raise AIError("AI-провайдер не настроен")
        if self.provider == "ollama":
            return self._ollama_chat(messages, json_mode)
        return self._openai_chat(messages, json_mode)

    def _openai_chat(self, messages: list[dict[str, str]], json_mode: bool) -> str:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": float(self.cfg.get("ai_temperature") or 0.1),
            "stream": False,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        r = self._post_openai("/chat/completions", payload)
        try:
            data = r.json()
            content = data["choices"][0]["message"]["content"]
            if isinstance(content, list):
                content = "".join(
                    p.get("text", "") for p in content if isinstance(p, dict)
                )
            return str(content or "").strip()
        except (KeyError, IndexError, ValueError) as exc:
            raise AIError("Некорректный ответ AI API") from exc

    def _ollama_chat(self, messages: list[dict[str, str]], json_mode: bool) -> str:
        base = self._ollama_base_url()
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": float(self.cfg.get("ai_temperature") or 0.1)},
        }
        if json_mode:
            payload["format"] = "json"
        try:
            with httpx.Client(timeout=self.timeout, follow_redirects=False) as client:
                r = client.post(base + "/api/chat", json=payload)
        except httpx.HTTPError as exc:
            raise AIError(f"Не удалось подключиться к Ollama: {exc}") from exc
        if r.status_code >= 400:
            raise AIError(f"Ollama вернула ошибку {r.status_code}: {r.text[:500]}")
        try:
            data = r.json()
            content = data.get("message", {}).get("content", "")
            return str(content or "").strip()
        except ValueError as exc:
            raise AIError("Некорректный ответ Ollama") from exc

    def list_models(self) -> list[str]:
        if self.provider == "ollama":
            base = self._ollama_base_url()
            try:
                with httpx.Client(timeout=min(self.timeout, 20), follow_redirects=False) as client:
                    r = client.get(base + "/api/tags")
                r.raise_for_status()
                return [m.get("name", "") for m in r.json().get("models", []) if m.get("name")]
            except Exception as exc:  # noqa: BLE001
                raise AIError(f"Не удалось получить список моделей Ollama: {exc}") from exc
        try:
            with httpx.Client(timeout=min(self.timeout, 25), follow_redirects=False) as client:
                r = client.get(self._openai_url("/models"), headers=self._headers())
            r.raise_for_status()
            return [m.get("id", "") for m in r.json().get("data", []) if m.get("id")]
        except Exception as exc:  # noqa: BLE001
            raise AIError(f"Не удалось получить список моделей: {exc}") from exc

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        if not self.available:
            raise AIError("Embeddings недоступны: AI-провайдер не настроен")
        if self.provider == "ollama":
            return self._ollama_embed(texts)
        return self._openai_embed(texts)

    def _openai_embed(self, texts: list[str]) -> list[list[float]]:
        payload = {
            "model": self.embedding_model,
            "input": texts,
        }
        r = self._post_openai("/embeddings", payload, retries=1)
        data = r.json().get("data", [])
        data.sort(key=lambda x: x.get("index", 0))
        return [d.get("embedding", []) for d in data]

    def _ollama_embed(self, texts: list[str]) -> list[list[float]]:
        base = self._ollama_base_url()
        model = self.embedding_model
        try:
            with httpx.Client(timeout=self.timeout, follow_redirects=False) as client:
                r = client.post(base + "/api/embed", json={"model": model, "input": texts})
                if r.status_code == 404:
                    r = client.post(
                        base + "/api/embeddings", json={"model": model, "prompt": texts[0]}
                    )
                    if r.status_code < 400:
                        return [r.json().get("embedding", [])]
                if r.status_code >= 400:
                    raise AIError(f"Ollama embeddings: {r.status_code} {r.text[:300]}")
                data = r.json()
                if "embeddings" in data:
                    return data["embeddings"]
                return [data.get("embedding", [])]
        except httpx.HTTPError as exc:
            raise AIError(f"Ошибка embeddings Ollama: {exc}") from exc

    def test(self) -> dict[str, Any]:
        if not self.available:
            return {"ok": False, "error": "Провайдер не настроен или не указан API-ключ"}
        started = time.monotonic()
        try:
            answer = self.chat(
                [
                    {"role": "system", "content": "Отвечай предельно кратко."},
                    {"role": "user", "content": "Ответь одним словом: ok"},
                ]
            )
            latency_ms = int((time.monotonic() - started) * 1000)
            return {
                "ok": True,
                "model": self.model,
                "response": answer[:200],
                "latency_ms": latency_ms,
            }
        except Exception as exc:  # noqa: BLE001
            error = str(exc)
            result: dict[str, Any] = {"ok": False, "model": self.model, "error": error}
            if self.provider != "ollama" and self._model_not_found(error):
                available = self._safe_models()
                if available:
                    result["available_models"] = available
                    sample = ", ".join(available[:12])
                    more = f" и ещё {len(available) - 12}" if len(available) > 12 else ""
                    result["hint"] = (
                        f"Модель «{self.model}» недоступна у провайдера. "
                        f"Доступные модели: {sample}{more}. "
                        "Выберите одну из них в поле «Модель»."
                    )
                else:
                    result["hint"] = (
                        f"Модель «{self.model}» недоступна у провайдера. "
                        "Загрузите список моделей и выберите доступную."
                    )
            return result

    def _safe_models(self) -> list[str]:
        try:
            return self.list_models()
        except Exception:  # noqa: BLE001
            return []


def get_ai_client(db) -> AIClient:
    from .runtime_settings import get_runtime_settings

    return AIClient(get_runtime_settings(db))
