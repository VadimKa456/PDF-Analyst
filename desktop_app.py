"""
Desktop launcher for PDF Analyst.

Запускает локальный FastAPI-сервер и открывает приложение в отдельном окне
(pywebview), без внешнего браузера. Если pywebview недоступен, открывает
системный браузер как запасной вариант.
"""
from __future__ import annotations

import logging
import multiprocessing
import os
import shutil
import socket
import sys
import threading
import time
import traceback
import webbrowser
from pathlib import Path


def _app_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
    return Path(__file__).resolve().parent


def _writable_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def _setup_paths() -> None:
    base = _app_base_dir()
    # В frozen-сборке код backend лежит внутри bundle; добавляем пути импорта.
    for p in (base, base / "backend"):
        sp = str(p)
        if sp not in sys.path:
            sys.path.insert(0, sp)
    os.chdir(str(_writable_dir()))


def _configure_logging() -> Path:
    log_dir = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "PDF Analyst" / "logs"
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
    except Exception:
        log_dir = _writable_dir()
    log_file = log_dir / "desktop.log"
    handlers: list[logging.Handler] = [logging.FileHandler(log_file, encoding="utf-8")]
    # В windowed-сборке (console=False) sys.stdout может быть None.
    stream = sys.stdout or sys.stderr
    if stream is not None:
        handlers.append(logging.StreamHandler(stream))
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        handlers=handlers,
    )
    return log_file


def _pick_port(preferred: int = 8000) -> int:
    env_port = os.environ.get("PORT", "").strip()
    if env_port.isdigit():
        preferred = int(env_port)
    for port in range(preferred, preferred + 20):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    # последний шанс: попросим ОС выбрать порт
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _wait_server(url: str, timeout: float = 60.0) -> bool:
    import urllib.request

    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url + "/api/health", timeout=2) as resp:
                if 200 <= resp.status < 500:
                    return True
        except Exception:
            time.sleep(0.3)
    return False


class DesktopApi:
    """Методы, доступные из JavaScript окна (window.pywebview.api)."""

    def save_export(self, source_path: str, suggested_name: str) -> str:
        """Показывает системный диалог сохранения и копирует туда файл экспорта.

        Возвращает выбранный путь или пустую строку (отмена/ошибка).
        """
        logger = logging.getLogger("pdf-analyst.desktop")
        try:
            source = Path(source_path)
            if not source.is_file():
                logger.error("Экспорт не найден: %s", source)
                return ""
            import webview

            window = webview.windows[0] if webview.windows else None
            if window is None:
                return ""
            target = window.create_file_dialog(
                webview.SAVE_DIALOG,
                save_filename=suggested_name or source.name,
            )
            if not target:
                return ""
            target_path = Path(target if isinstance(target, str) else target[0])
            target_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target_path)
            logger.info("Экспорт сохранён: %s", target_path)
            return str(target_path)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Не удалось сохранить экспорт: %s", exc)
            return ""


def _show_error(title: str, message: str, log_file: Path | None = None) -> None:
    text = message
    if log_file:
        text += f"\n\nЛог: {log_file}"
    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(None, text, title, 0x10)
    except Exception:
        print(f"{title}\n{text}", file=sys.stderr)


def main() -> int:
    multiprocessing.freeze_support()
    _setup_paths()
    log_file = _configure_logging()
    logger = logging.getLogger("pdf-analyst.desktop")

    try:
        import uvicorn
        from backend.app.config import settings
        from backend.app.main import app as fastapi_app
    except Exception as exc:
        logger.exception("Import failed")
        _show_error(
            "PDF Analyst — ошибка запуска",
            "Не удалось загрузить приложение.\n"
            f"{exc}\n\n{traceback.format_exc(limit=3)}",
            log_file,
        )
        return 1

    # The desktop API has no authentication yet; never expose it on LAN interfaces.
    # Ignore HOST from the environment to keep the listener loopback-only.
    host = "127.0.0.1"
    port = _pick_port(int(getattr(settings, "port", 8000) or 8000))
    url = f"http://{host}:{port}"

    config = uvicorn.Config(
        fastapi_app,
        host=host,
        port=port,
        log_level="info",
        access_log=False,
        reload=False,
        # Логирование уже настроено в _configure_logging(); dictConfig uvicorn
        # падает в windowed-сборке (нет sys.stdout → formatter 'default').
        log_config=None,
    )
    server = uvicorn.Server(config)

    # В desktop-режиме управляем shutdown сами при закрытии окна.
    # Отключаем стандартные обработчики сигналов uvicorn в не-main-потоке.
    # В uvicorn >=0.30 это capture_signals — контекстный менеджер (`with ...:`),
    # поэтому подменяем на nullcontext, а не на lambda (иначе TypeError).
    from contextlib import nullcontext

    try:
        if hasattr(server, "capture_signals"):
            server.capture_signals = nullcontext  # type: ignore[assignment]
        else:
            server.install_signal_handlers = lambda: None  # type: ignore[assignment]
    except Exception:
        pass

    thread = threading.Thread(target=server.run, daemon=True, name="uvicorn")
    thread.start()

    if not _wait_server(url, timeout=60.0):
        logger.error("Server did not start at %s", url)
        _show_error(
            "PDF Analyst — ошибка запуска",
            "Локальный сервер не запустился вовремя.",
            log_file,
        )
        try:
            server.should_exit = True
        except Exception:
            pass
        return 1

    logger.info("Server ready at %s", url)

    def _shutdown() -> None:
        try:
            server.should_exit = True
        except Exception:
            pass
        try:
            from backend.app.services import jobs

            jobs.shutdown()
        except Exception:
            pass

    # Пытаемся открыть как desktop-окно (без браузера).
    try:
        import webview  # type: ignore

        window = webview.create_window(
            "PDF Analyst",
            url,
            js_api=DesktopApi(),
            width=1400,
            height=960,
            min_size=(1024, 720),
            confirm_close=True,
            text_select=True,
        )

        def on_closed():
            _shutdown()

        try:
            window.events.closed += on_closed
        except Exception:
            pass

        # На Windows предпочтителен edgechromium (WebView2), если доступен.
        gui = None
        if sys.platform.startswith("win"):
            gui = "edgechromium"
        try:
            webview.start(gui=gui, debug=False)
        except Exception:
            # fallback на доступный backend webview
            webview.start(debug=False)
        _shutdown()
        return 0
    except Exception as exc:
        logger.warning("pywebview unavailable/failed: %s; falling back to browser", exc)
        webbrowser.open(url)
        # Держим сервер живым, пока процесс не завершён пользователем.
        try:
            while thread.is_alive():
                time.sleep(0.5)
        except KeyboardInterrupt:
            pass
        _shutdown()
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
