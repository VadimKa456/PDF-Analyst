# Готовые тексты для объявления проекта

Скопируйте нужный вариант и замените ссылки, если публикуете не от аккаунта `VadimKa456`.

Основные ссылки:
- Репозиторий: https://github.com/VadimKa456/PDF-Analyst
- Скачать установщик: https://github.com/VadimKa456/PDF-Analyst/releases/latest
- Страница релиза: https://github.com/VadimKa456/PDF-Analyst/releases/tag/v1.1.0
- Скриншот: https://github.com/VadimKa456/PDF-Analyst/blob/main/screenshots/desktop-dashboard.png

---

## 1. Elevator pitch (одно предложение)

> PDF Analyst — локальное приложение для анализа PDF с OCR, таблицами, AI-аналитиком и экспортом: каждое число имеет ссылку на страницу документа, а полные PDF никогда не уходят в облако.

English:

> PDF Analyst is a local-first PDF analysis app with OCR, tables, an offline AI analyst and source-linked numbers — full documents never leave your machine.

---

## 2. Короткий пост (Telegram, VK, LinkedIn, Reddit)

> **Representing VADIJI | AI Creative Studio: PDF Analyst v1.1.0**
>
> Локальное приложение для анализа и сравнения PDF на русском и английском языках.
>
> • OCR сканов (Tesseract + OpenCV, rus/eng)
> • Извлечение таблиц, чисел, дат, единиц и периодов
> • AI-аналитик — работает и полностью офлайн
> • Каждое число со ссылкой на страницу и фрагмент
> • Экспорт Excel / CSV / PDF / PNG
> • Отдельное окно Windows 10/11, а не браузер
> • MIT License
>
> Скачать: https://github.com/VadimKa456/PDF-Analyst/releases/latest
> Исходники и документация: https://github.com/VadimKa456/PDF-Analyst
>
> Буду рад звёздам ⭐, issue и идеям!

English version (Reddit r/Python, r/selfhosted, r/opensource):

> **PDF Analyst v1.1.0 — local-first PDF analysis (Windows desktop app)**
>
> - OCR for scanned PDFs (Tesseract + OpenCV, rus/eng)
> - Table, number, date, unit and period extraction
> - Deterministic local AI analyst; optional OpenAI-compatible/Ollama
> - Every number linked to its document page and snippet
> - Excel / CSV / PDF / PNG export
> - Runs in its own window, not a browser; MIT licensed
> - No full PDF or document text ever sent to the cloud
>
> Installer: https://github.com/VadimKa456/PDF-Analyst/releases/latest
> Source: https://github.com/VadimKa456/PDF-Analyst
>
> Feedback, issues and stars welcome ⭐

---

## 3. Habr — заголовок и лид

**Заголовок:**
«PDF Analyst: локальный анализ PDF с OCR, RAG и честными источниками чисел»

**Лид:**
> Онлайн-сервисы анализа PDF удобны, но требуют загрузки документов в облако. Рассказываю об открытом локальном инструменте, который извлекает таблицы, числа и периоды из сканов, отвечает на вопросы по документам и прикрепляет к каждому значению ссылку на страницу-источник. Исходники — на GitHub под MIT, готовый установщик — для Windows 10/11.

**Теги:** `Open Source`, `Python`, `PDF`, `Машинное обучение`, `Разработка`

**Структура статьи:**
1. Проблема: документы нельзя отправлять в облако, а ручной разбор таблиц долгий.
2. Архитектура: FastAPI + SQLite/FTS5 + PyMuPDF/Tesseract + React/Plotly.
3. Сложный кейс 1: OCR терял `1`/`0` в узких колонках — как чинили multi-pass OCR с учётом найденных чисел.
4. Сложный кейс 2: «висячая» десятичная запятая (`1153233 ,` → `11 532,33`) и завышение сумм в 100 раз.
5. Как работает проверка LLM на выдуманные числа.
6. Демо (скриншот + 30 секунд видео) и ссылка на Release.

---

## 4. Product Hunt — tagline и первый комментарий

**Tagline:** «Analyze PDFs locally — with sources, not uploads»

**Description:**
> PDF Analyst turns scanned and digital PDFs into structured tables, numbers and insights — entirely on your machine. Every value links back to the original page. Works offline in a native Windows app.

**First comment:**
> Hi Product Hunt! I built PDF Analyst because sending contracts and payroll PDFs to cloud AI felt wrong. It extracts tables, numbers, dates and units via PyMuPDF/Tesseract, answers questions with a deterministic local engine (or optionally your own OpenAI-compatible model), and validates that no invented numbers appear in answers. Desktop app for Windows 10/11, MIT licensed. Would love feedback on OCR quality and export formats!

---

## 5. LinkedIn — пост от автора

> За последние месяцы мы в VADIJI | AI Creative Studio собрали инструмент, которым сами пользовались: **PDF Analyst**.
>
> Это локальное приложение, которое читает PDF (включая сканы), находит таблицы и числа, отвечает на вопросы и экспортирует результаты. Ключевое отличие — каждое число ведёт к странице и фрагменту исходного документа, а полные файлы никуда не отправляются.
>
> Версия 1.1.0: удаление проектов, раздел «О программе», MIT-лицензия, исправленный экспорт и OCR мелких цифр. Установщик для Windows 10/11, исходники открыты.
>
> Ссылка в комментариях 👇 Буду рад, если попробуете и напишете, что улучшить.

---

## 6. SPI для рассылок/блога (3 абзаца)

**A local alternative to cloud PDF tools.** PDF Analyst runs on your computer: PyMuPDF handles digital PDFs, Tesseract + OpenCV handle scans, and SQLite FTS5 powers retrieval. No full document is ever transmitted to an external service.

**Verified numbers, not guesses.** Metrics carry page, snippet, unit and period. The built-in analytics engine computes deltas with transparent formulas; if an external LLM is enabled, its answer is rejected when it contains numbers absent from the verified data.

**Desktop-first delivery.** Version 1.1.0 ships as a single Windows installer with native Save As dialogs for exports, project management, and a 100% GitHub Community Standards profile.

---

## Чек-лит перед публикацией

- [ ] Приложить скриншот `screenshots/desktop-dashboard.png`
- [ ] Дать прямую ссылку на Release, а не только на репозиторий
- [ ] Упомянуть MIT и автора VADIJI | AI Creative Studio
- [ ] Отвечать на комментарии в первый день в течение нескольких часов
- [ ] Не публиковать конфиденциальные PDF в примерах — только `samples/`
