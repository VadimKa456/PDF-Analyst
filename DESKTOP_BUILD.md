# Сборка desktop-приложения и установщика (Windows)

Этот документ описывает, как собрать **PDF Analyst** как отдельное Windows-приложение (без внешнего браузера) и упаковать его в установщик.

## Готовый результат (собран 19.11.2026, проверен)

**Готовый установщик публикуется в [GitHub Releases](https://github.com/VadimKa456/PDF-Analyst/releases/latest):**
[`PDF-Analyst-Setup.exe`](https://github.com/VadimKa456/PDF-Analyst/releases/download/v1.1.0/PDF-Analyst-Setup.exe) (172 670 359 байт, Windows 10/11 x64).

> Каталоги `dist/` и `build/` **не коммитятся в Git** — это порождаемые артефакты.
> Их можно получить только локальной сборкой (`build_desktop.bat`) или скачать
> готовый `.exe` из Releases.

| Источник | Назначение |
|----------|------------|
| [GitHub Release v1.1.0](https://github.com/VadimKa456/PDF-Analyst/releases/tag/v1.1.0) | **Один файл установщика** (~172 МБ). SHA256: `69E661C2C7F5EB9AEFCEB6D6162A635396E42E8535052804727FCAB03CCE857E` (MIT-лицензия; логотип VADIJI; исправлены скачивание отчётов и OCR мелких чисел) |
| `dist\PDF Analyst\PDF Analyst.exe` (после локальной сборки) | Портативная версия (папка целиком, без установки) |

Установщик проверен: тихая установка во временный каталог → запуск → окно приложения → API `/api/health` → загрузка PDF → обработка (показатели и таблица извлечены) — без ошибок.

### Что делает установщик с недостающими компонентами
На шаге «Готово к установке» он проверяет:
- **Microsoft Edge WebView2 Runtime** (нужен для отдельного окна без браузера);
- **Visual C++ Redistributable 2015-2022 x64** (библиотеки NumPy/OpenCV/PyMuPDF и др.);
- **Tesseract OCR** (только для распознавания сканов — необязателен).

Если что-то отсутствует, появляется запрос. При согласии WebView2 и VC++ скачиваются с официальных ссылок и устанавливаются тихо; для Tesseract открывается страница загрузки (нужно установить с языками `rus` и `eng`). Установка приложения продолжается в любом случае.

### Важно про окно
Приложение работает в **собственном окне** (`pywebview` + Edge WebView2), а не в окне браузера. Fallback в системный браузер используется только если WebView2/pywebview недоступны — поэтому установщик и запрашивает WebView2.

### Лицензии и сторонние компоненты
Исходный код проекта PDF Analyst сопровождается лицензией **MIT** (`LICENSE`).
Эта лицензия не отменяет условий сторонних библиотек, которые включаются в
установщик. В частности, PyMuPDF/MuPDF распространяется по AGPLv3 либо по
отдельной коммерческой лицензии Artifex. До коммерческого распространения
необходимо выбрать и документировать подходящий вариант. Подробности и
варианты действий: [docs/LICENSING_REVIEW.md](docs/LICENSING_REVIEW.md).

Новая desktop-сборка включает каталог `compliance/` с SBOM Python/npm,
зафиксированными версиями установленного окружения, перечнем объявленных
лицензий и доступными текстами third-party notices. Это инвентаризация, а не
подтверждение юридического соответствия; строки UNKNOWN и отсутствующие тексты
требуют ручной проверки. Опубликованный `v1.1.0` был собран до появления этого
механизма и такого каталога не содержит.

Файл проекта `LICENSE` остаётся включён в установщик; в приложении текст
лицензии проекта доступен в разделе «О программе» через `/LICENSE.txt`.

### Экспорт файлов (отчёты, графики)
WebView2 ненадёжно скачивает файлы через `blob + <a download>`. Поэтому:
- сервер дополнительно сохраняет каждый экспорт в `%LOCALAPPDATA%\PDF Analyst\data\exports` и возвращает путь в заголовке `X-Saved-Path`;
- desktop-приложение через `window.pywebview.api.save_export()` открывает системный диалог **«Сохранить как»** и копирует туда готовый файл; в уведомлении показан выбранный путь;
- в обычном браузере используется обычное скачивание (ссылка добавляется в DOM, `URL.revokeObjectURL` откладывается на 60 с, чтобы браузер не отменил загрузку).

## Важно: совместимость

- **Поддерживаемая целевая сборка:** Windows 10 / 11, x64.
- **Windows 7:** текущая кодовая база использует **Python 3.12** и современные бинарные зависимости (PyMuPDF, OpenCV, NumPy, pandas, cryptography-стек зависимостей и т.д.). Python 3.12 и актуальные колёса этих библиотек **не поддерживают Windows 7**, поэтому «единый установщик для 7/10/11» на этой версии стека технически невозможен без отдельного портирования на устаревший Python (≤3.8) и совместимые версии всех зависимостей. Для Win7 требуется отдельная legacy-сборка.
- **OCR (Tesseract):** не входит в установщик приложения. Для распознавания сканов установите Tesseract OCR отдельно и укажите путь в настройках приложения (`TESSERACT_CMD` / раздел «Настройки»). Приложение автоматически ищет Tesseract в стандартных путях `%LOCALAPPDATA%\Programs\Tesseract-OCR` и `Program Files`.

## Что создаётся

1. **Desktop-режим:** `desktop_app.py` запускает локальный сервер FastAPI и открывает UI в отдельном окне через `pywebview` (без браузера). При отсутствии/ошибке WebView выполняется fallback в системный браузер.
2. **Портативная сборка:** `dist/PDF Analyst/PDF Analyst.exe` (+ файлы рядом) — папка, которую можно запускать/копировать.
3. **Защита локального API:** desktop launcher всегда привязывает сервер к `127.0.0.1` (переменная окружения `HOST` игнорируется). На каждый запуск генерируется новый случайный секрет; первая верхнеуровневая навигация окна устанавливает `HttpOnly; SameSite=Strict` cookie. Все `/api` маршруты требуют cookie, а сервер проверяет `Host`, `Origin` и Fetch Metadata. Секрет не передаётся в URL, localStorage или обычный frontend JavaScript.
4. **Установщик (один .exe):** `dist/installer/PDF-Analyst-Setup.exe` — создаётся Inno Setup из портативной сборки.

## Данные пользователя

- В dev-режиме: `./data` в каталоге проекта (как раньше).
- В упакованном приложении: `%LOCALAPPDATA%\PDF Analyst\data` (БД, загрузки, экспорты) — чтобы запись работала без прав администратора и после установки в `Program Files`.
- Логи desktop-запуска: `%LOCALAPPDATA%\PDF Analyst\logs\desktop.log`.
- Путь к данным можно переопределить переменной окружения `DATA_DIR` (абсолютный или относительный).

## Предварительные требования для сборки

- Windows 10/11 x64
- Python 3.12 x64 и bootstrap-окружение `.venv` (создаётся через `setup.bat`)
- Зафиксированный `requirements-desktop-lock.txt` (генерируется и проверяется GitHub Actions для Windows/Python 3.12)
- Node.js 22 и npm для воспроизводимой сборки frontend из `package-lock.json`
- [Inno Setup 6](https://jrsoftware.org/isinfo.php) — только если нужен установщик `.exe` (ISCC)

## Быстрая сборка

Из корня проекта:

```bat
build_desktop.bat
```

Скрипт:
- проверяет, что bootstrap `.venv` использует CPython 3.12;
- удаляет прежний `.build-venv` и создаёт новое чистое окружение;
- устанавливает Python-зависимости только из `requirements-desktop-lock.txt` с проверкой SHA-256 через `pip --require-hashes`;
- выполняет `pip check` и полный backend `pytest` внутри этого locked-окружения;
- выполняет `npm ci` и `npm run build`, если Node.js/npm доступны; без npm использует существующий frontend/dist с предупреждением;
- запускает `pyinstaller --noconfirm --clean pdf_analyst.spec` из locked-окружения;
- создаёт `compliance/` с точным снимком установленных компонентов и лицензий;
- компилирует `installer.iss`, если найден Inno Setup 6. Для CI можно задать `PDF_ANALYST_SKIP_INSTALLER=1`, чтобы проверить portable-сборку без Inno Setup.

## Ручная сборка

Рекомендуемый ручной запуск — тот же проверяемый сценарий, что и в CI:

```bat
setup.bat
build_desktop.bat
```

При необходимости можно выполнить шаги отдельно:

```bat
.venv\Scripts\python.exe -m venv .build-venv
.build-venv\Scripts\python.exe -m pip install --require-hashes -r requirements-desktop-lock.txt
.build-venv\Scripts\python.exe -m pip check
.build-venv\Scripts\python.exe -m pytest -q
cd frontend && npm ci && npm run build && cd ..
.build-venv\Scripts\python.exe -m PyInstaller --noconfirm --clean pdf_analyst.spec
.build-venv\Scripts\python.exe tools\generate_compliance_inventory.py --output-dir "dist\PDF Analyst\compliance" --frontend-node-modules "frontend\node_modules"
"C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer.iss
```

### Как обновляется Python lock

Входные диапазоны для release-окружения находятся в `requirements-desktop.in`.
GitHub Actions на Windows/Python 3.12 запускает зафиксированный `pip-tools`,
генерирует `requirements-desktop-lock.txt` с hashes, затем устанавливает его
в чистое окружение, выполняет `pip check` и backend tests. Только после успеха
job сохраняет lock в PR-ветку. Не редактируйте lock вручную: меняйте input-файлы
и проверяйте новый lock через CI.

## Режимы PyInstaller

В `pdf_analyst.spec` по умолчанию `onefile = False` (**onedir**, рекомендуется):
- быстрее старт, проще отладка, меньше проблем с антивирусами/распаковкой;
- установщик Inno Setup упаковывает всю папку в **один файл установщика** (что обычно и требуется).

`onefile = True` создаёт один исполняемый файл, но увеличивает время запуска и может требовать дополнительной настройки исключений антивируса.

## SBOM и сторонние лицензии

При выполнении `build_desktop.bat` в `dist/PDF Analyst/compliance/` создаются
CycloneDX JSON-инвентари Python-окружения и frontend lockfile, снимок
`pip freeze --all`, список объявленных лицензий и доступные тексты notices.
Каталог включается в установщик рекурсивным правилом Inno Setup. Если
`frontend/node_modules` отсутствует, npm SBOM всё равно строится из
`package-lock.json`, но тексты frontend-лицензий могут не скопироваться.

Python build-окружение устанавливается из `requirements-desktop-lock.txt`
с SHA-256 hashes; inventory дополнительно сохраняет установленный `pip freeze`
и SBOM. Frontend устанавливается из `package-lock.json` через `npm ci`.
Эти файлы фиксируют версии, но сами по себе не подтверждают юридическую
совместимость. Обязательно прочитайте
[LICENSING_REVIEW.md](docs/LICENSING_REVIEW.md) и
`compliance/THIRD_PARTY_NOTICES.md` перед коммерческим распространением.

## Проверка после сборки

1. Запустите `dist\PDF Analyst\PDF Analyst.exe`.
2. Убедитесь, что окно приложения открылось, UI загрузился, `/api/health` отвечает.
3. Проверьте загрузку PDF, обработку, анализ, экспорт.
4. Для OCR установите Tesseract с `rus`/`eng` и проверьте в настройках.

## Ограничения обработки PDF и AI endpoints

- PDF: максимум 500 страниц и 1 ГБ (вдобавок к пользовательскому лимиту загрузки).
- Ограничения текста: 500 000 символов на страницу и 5 млн на документ.
- Растр OCR/предпросмотра: не более 12 млн пикселей; OCR не снижается ниже 150 DPI.
- Tesseract OCR: общий лимит 30 секунд на страницу; по тайм-ауту сохраняется лучший уже распознанный вариант, иначе страница отмечается предупреждением.
- Удалённые OpenAI-compatible/Ollama endpoints должны использовать HTTPS. HTTP поддерживается только для loopback (например, `http://127.0.0.1:11434`). Для кастомного провайдера используйте доверенный URL.

## Примечания

- В сборку включаются тяжёлые зависимости (NumPy/Pandas/OpenCV/PyMuPDF/Matplotlib/ReportLab) — размер дистрибутива будет большим.
- Для работы окна на Windows 10/11 предпочтителен Microsoft Edge WebView2 Runtime (обычно уже установлен). При его отсутствии pywebview может использовать другой backend или приложение откроет UI в системном браузере.
- Сетевой доступ к облачным AI/моделям определяется настройками пользователя; по умолчанию `AI_PROVIDER=none` (локальная обработка).
