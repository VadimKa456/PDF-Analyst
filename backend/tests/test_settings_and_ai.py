"""Настройки AI/OCR, маскирование ключей и защита от утечки документов."""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base
from app.api.settings import _validate_patch
from fastapi import HTTPException
from app.services.ai_client import AIClient, AIError
from app.services.ai_url import validate_ai_base_url
from app.services.query_engine import (
    _allowed_numbers,
    _docs_payload,
    _refine_with_ai,
    _validate_ai_text,
)
from app.services.runtime_settings import (
    default_runtime_settings,
    get_runtime_settings,
    public_settings,
    save_runtime_settings,
)


@pytest.fixture()
def db() -> Session:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def test_default_settings_have_required_sections(db: Session) -> None:
    settings = get_runtime_settings(db)
    for key in (
        "ai_provider",
        "ollama_model",
        "openai_model",
        "ocr_enabled",
        "ocr_languages",
        "export_page_size",
    ):
        assert key in settings
    assert settings["ai_provider"] in {"none", "openai", "ollama"}


def test_settings_are_persisted_and_unknown_keys_ignored(db: Session) -> None:
    save_runtime_settings(
        db,
        {"ollama_model": "llama3.2", "unknown_option": "must be ignored"},
    )
    stored = get_runtime_settings(db)
    assert stored["ollama_model"] == "llama3.2"
    assert "unknown_option" not in stored


def test_public_settings_mask_api_key(db: Session) -> None:
    save_runtime_settings(
        db,
        {
            "ai_provider": "openai",
            "openai_api_key": "sk-test-1234567890abcdef",
        },
    )
    public = public_settings(db)
    assert public["openai_api_key"] == ""
    assert "1234567890ab" not in public["openai_api_key_masked"]
    assert public["openai_api_key_masked"].startswith("sk-t")
    assert public["openai_api_key_masked"].endswith("cdef")
    # ключ сохранён для работы, но наружу не отдаётся
    assert get_runtime_settings(db)["openai_api_key"] == "sk-test-1234567890abcdef"


def test_ai_configured_reflects_provider(db: Session) -> None:
    save_runtime_settings(db, {"ai_provider": "none", "openai_api_key": "sk-123"})
    assert public_settings(db)["ai_configured"] is False

    save_runtime_settings(db, {"ai_provider": "openai", "openai_api_key": "sk-123"})
    assert public_settings(db)["ai_configured"] is True

    save_runtime_settings(db, {"ai_provider": "openai", "openai_api_key": ""})
    assert public_settings(db)["ai_configured"] is False

    save_runtime_settings(db, {"ai_provider": "ollama"})
    assert public_settings(db)["ai_configured"] is True


def test_ai_client_availability_does_not_require_network() -> None:
    assert AIClient({"ai_provider": "none"}).available is False
    assert AIClient({"ai_provider": "openai", "openai_api_key": ""}).available is False
    assert (
        AIClient(
            {"ai_provider": "openai", "openai_api_key": "sk-x", "openai_base_url": "https://x/v1"}
        ).available
        is True
    )
    assert (
        AIClient(
            {"ai_provider": "openai", "openai_api_key": "sk-x", "openai_base_url": "http://x/v1"}
        ).available
        is False
    )
    assert AIClient({"ai_provider": "ollama", "ollama_base_url": "http://localhost:11434"}).available


@pytest.mark.parametrize(
    "url",
    [
        "http://provider.example/v1",
        "http://192.168.1.20:11434",
        "http://10.0.0.5:8000",
        "https://provider.example/v1?mode=test",
        "https://service.internal/v1",
        "https://bad_host.example/v1",
        "https://provider.example:0/v1",
        "file:///tmp/sample",
    ],
)
def test_ai_endpoint_validation_rejects_unsafe_urls(url: str) -> None:
    with pytest.raises(ValueError):
        validate_ai_base_url(url)


def test_ai_endpoint_validation_allows_https_and_loopback_http() -> None:
    assert validate_ai_base_url("https://provider.example/v1") == "https://provider.example/v1"
    assert validate_ai_base_url("http://127.0.0.1:11434/") == "http://127.0.0.1:11434"


def test_settings_reject_remote_ai_endpoints_over_plain_http() -> None:
    with pytest.raises(HTTPException) as error:
        _validate_patch({"openai_base_url": "http://provider.example/v1"})
    assert error.value.status_code == 422
    assert "HTTPS" in str(error.value.detail)


def test_local_mode_never_calls_ai() -> None:
    client = AIClient({"ai_provider": "none"})
    with pytest.raises(AIError):
        client.chat([{"role": "user", "content": "test"}])


def test_openai_url_does_not_duplicate_v1() -> None:
    with_v1 = AIClient(
        {"ai_provider": "openai", "openai_api_key": "sk-x", "openai_base_url": "https://anymodel.org/v1"}
    )
    assert with_v1._openai_url("/chat/completions") == "https://anymodel.org/v1/chat/completions"
    without_v1 = AIClient(
        {"ai_provider": "openai", "openai_api_key": "sk-x", "openai_base_url": "https://anymodel.org"}
    )
    assert without_v1._openai_url("/chat/completions") == "https://anymodel.org/v1/chat/completions"


def test_model_not_found_error_explains_what_to_do() -> None:
    client = AIClient(
        {
            "ai_provider": "openai",
            "openai_api_key": "sk-x",
            "openai_base_url": "https://anymodel.org/v1",
            "openai_model": "gpt-4o-mini",
        }
    )
    message = client._describe_http_error(404, '{"code":"model_not_found"}')
    assert "gpt-4o-mini" in message
    assert "Список моделей" in message
    assert "ключ" in client._describe_http_error(401, "unauthorized")


class _FakeChatClient(AIClient):
    def __init__(self, cfg, answer: str = "ok", error: str | None = None, models=None):
        super().__init__(cfg)
        self.answer = answer
        self.error = error
        self._models = models or []

    def chat(self, messages, json_mode: bool = False) -> str:
        if self.error:
            raise AIError(self.error)
        return self.answer

    def list_models(self) -> list[str]:
        return self._models


def _openai_cfg() -> dict:
    return {
        "ai_provider": "openai",
        "openai_api_key": "sk-test",
        "openai_base_url": "https://example.invalid/v1",
        "openai_model": "gpt-4o-mini",
    }


def test_ai_test_returns_latency() -> None:
    result = _FakeChatClient(_openai_cfg()).test()
    assert result["ok"] is True
    assert result["response"] == "ok"
    assert result["latency_ms"] >= 0


def test_ai_test_suggests_available_models_on_404() -> None:
    client = _FakeChatClient(
        _openai_cfg(),
        error='AI API вернул ошибку 404: {"code":"model_not_found"}',
        models=["glm/glm-4.7", "am/free"],
    )
    result = client.test()
    assert result["ok"] is False
    assert result["available_models"] == ["glm/glm-4.7", "am/free"]
    assert "glm/glm-4.7" in result["hint"]
    assert "недоступна" in result["hint"]


class _FakeOpenAIHandler(BaseHTTPRequestHandler):
    seen: list[tuple[str, str | None]] = []
    flaky_calls = 0

    def _send(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        type(self).seen.append((self.path, self.headers.get("Authorization")))
        if self.path.startswith("/redirect/"):
            self.send_response(302)
            self.send_header("Location", "/v1/models")
            self.end_headers()
            return
        if self.path.endswith("/models"):
            self._send({"data": [{"id": "test-model"}]})
        else:
            self._send({"error": "not found"}, 404)

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length") or 0)
        payload = json.loads(self.rfile.read(length) or b"{}")
        type(self).seen.append((self.path, self.headers.get("Authorization")))
        if self.path.endswith("/chat/completions"):
            if self.path.startswith("/flaky/"):
                type(self).flaky_calls += 1
                if type(self).flaky_calls <= 2:
                    self._send(
                        {
                            "error": {
                                "message": "The upstream provider is temporarily unavailable.",
                                "retry_after_seconds": 0,
                            }
                        },
                        503,
                    )
                    return
            self._send({"choices": [{"message": {"content": "ok"}}]})
        elif self.path.endswith("/embeddings"):
            count = len(payload.get("input") or [])
            self._send({"data": [{"index": i, "embedding": [0.1, 0.2]} for i in range(count)]})
        else:
            self._send({"error": "not found"}, 404)

    def log_message(self, *args) -> None:
        pass


@pytest.fixture()
def fake_openai() -> str:
    _FakeOpenAIHandler.seen = []
    _FakeOpenAIHandler.flaky_calls = 0
    server = ThreadingHTTPServer(("127.0.0.1", 0), _FakeOpenAIHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}/v1"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_openai_compatible_api_round_trip(fake_openai: str) -> None:
    client = AIClient(
        {
            "ai_provider": "openai",
            "openai_api_key": "sk-test",
            "openai_base_url": fake_openai,
            "openai_model": "test-model",
            "ai_timeout_seconds": 5,
        }
    )
    result = client.test()
    assert result["ok"] is True, result
    assert result["model"] == "test-model"

    assert client.list_models() == ["test-model"]
    vectors = client.embed(["a", "b"])
    assert vectors == [[0.1, 0.2], [0.1, 0.2]]

    paths = [path for path, _ in _FakeOpenAIHandler.seen]
    assert paths == ["/v1/chat/completions", "/v1/models", "/v1/embeddings"]
    assert all(auth == "Bearer sk-test" for _, auth in _FakeOpenAIHandler.seen)


def test_openai_client_does_not_follow_redirects_with_api_key(fake_openai: str) -> None:
    client = AIClient(
        {
            "ai_provider": "openai",
            "openai_api_key": "sk-test",
            "openai_base_url": fake_openai.replace("/v1", "/redirect/v1"),
            "openai_model": "test-model",
            "ai_timeout_seconds": 5,
        }
    )

    with pytest.raises(AIError):
        client.list_models()

    paths = [path for path, _ in _FakeOpenAIHandler.seen]
    assert paths == ["/redirect/v1/models"]


def test_openai_retries_transient_503(fake_openai: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.services.ai_client.time.sleep", lambda _seconds: None)
    client = AIClient(
        {
            "ai_provider": "openai",
            "openai_api_key": "sk-test",
            "openai_base_url": fake_openai.replace("/v1", "/flaky/v1"),
            "openai_model": "test-model",
            "ai_timeout_seconds": 5,
        }
    )
    result = client.test()
    assert result["ok"] is True, result
    assert result["latency_ms"] >= 0
    assert _FakeOpenAIHandler.flaky_calls == 3


def test_documents_payload_does_not_include_file_contents() -> None:
    doc = SimpleNamespace(
        id=1,
        original_name="alpha_2024.pdf",
        page_count=1,
        status="ready",
        ocr_pages=0,
        avg_confidence=0.98,
        file_path="C:/secret/path/alpha_2024.pdf",
        text="полный текст документа, который нельзя отправлять",
    )
    payload = _docs_payload([doc])
    assert payload == [
        {
            "id": 1,
            "name": "alpha_2024.pdf",
            "pages": 1,
            "status": "ready",
            "ocr_pages": 0,
            "avg_confidence": 0.98,
        }
    ]
    dumped = json.dumps(payload, ensure_ascii=False)
    assert "secret" not in dumped
    assert "полный текст" not in dumped


class _FakeClient:
    available = True
    model = "fake-model"

    def __init__(self, answer: str):
        self.answer = answer
        self.captured: list[list[dict[str, str]]] = []

    def chat(self, messages, json_mode: bool = False) -> str:
        self.captured = messages
        return self.answer


def _ai_result() -> dict:
    return {
        "tables": [
            {
                "title": "Сравнение выручки",
                "columns": [{"label": "Показатель"}, {"label": "Значение"}],
                "rows": [
                    {
                        "indicator": "Выручка",
                        "value_display": "120 млн руб.",
                        "source_document": "beta_2024.pdf",
                        "source_page": 4,
                        "source_snippet": "Revenue — 120 млн руб.",
                    }
                ],
            }
        ],
        "findings": ["Выручка Beta — 120 млн руб. (beta_2024.pdf, стр. 4)"],
        "warnings": [],
        "summary": "Выручка Beta 120 млн руб.",
        "methods": [],
        "meta": {},
        "documents": [{"id": 2, "name": "beta_2024.pdf", "pages": 1}],
    }


def test_ai_receives_only_structured_facts_not_full_documents() -> None:
    client = _FakeClient(
        json.dumps(
            {"summary": "Выручка Beta — 120 млн руб. [beta_2024.pdf, стр. 4]", "key_points": []},
            ensure_ascii=False,
        )
    )
    result = _ai_result()
    result["documents"][0]["full_text"] = "СЕКРЕТНЫЙ ПОЛНЫЙ ТЕКСТ ДОКУМЕНТА"

    text, meta = _refine_with_ai(client, "Сравни выручку", result, "Выручка Beta 120")

    assert meta["ai_used"] is True
    assert text and "120" in text
    prompt = client.captured[1]["content"]
    # в облако уходят только структурированные факты, но не файл PDF целиком
    assert "СЕКРЕТНЫЙ ПОЛНЫЙ ТЕКСТ" not in prompt
    assert "beta_2024.pdf" in prompt


def test_ai_hallucinated_number_is_rejected() -> None:
    client = _FakeClient(json.dumps({"summary": "Выручка Beta — 999 млн руб.", "key_points": []}))
    text, meta = _refine_with_ai(client, "Сравни выручку", _ai_result(), "Выручка Beta 120")
    assert text is None
    assert meta["ai_used"] is False
    assert "999" in meta["ai_error"]


def test_ai_answer_with_supported_numbers_is_accepted() -> None:
    facts = _ai_result()
    allowed = _allowed_numbers(facts)
    ok, reason = _validate_ai_text("Выручка 120 млн руб., стр. 4.", allowed)
    assert ok and reason is None

def test_openai_client_ignores_untrusted_proxy_environment(
    fake_openai: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A user- or machine-level proxy must not silently receive the API key.
    for name in ("HTTP_PROXY", "http_proxy", "HTTPS_PROXY", "https_proxy"):
        monkeypatch.setenv(name, "http://127.0.0.1:1")
    monkeypatch.setenv("NO_PROXY", "")
    monkeypatch.setenv("no_proxy", "")

    client = AIClient(
        {
            "ai_provider": "openai",
            "openai_api_key": "sk-test",
            "openai_base_url": fake_openai,
            "openai_model": "test-model",
            "ai_timeout_seconds": 5,
        }
    )
    assert client.list_models() == ["test-model"]
