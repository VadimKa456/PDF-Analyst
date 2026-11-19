# Как внести вклад в PDF Analyst

Спасибо за интерес к проекту! Ниже — правила и пошаговые инструкции.

## Кодекс поведения

Участие в проекте регулируется [Code of Conduct](.github/CODE_OF_CONDUCT.md).

## Что приветствуется

- Исправления ошибок (KR/OCR, таблицы, числа, экспорт, UI).
- Улучшения документации и переводов.
- Новые тесты и расширение покрытия.
- Идеи и запросы функций — через Issue с шаблоном **Feature request**.

## Подготовка окружения

Требуется **Python 3.11+** (проверено на 3.12), **Node.js 18+** для frontend и
**Tesseract OCR** с языками `rus+eng` для тестов OCR.

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
cd frontend
npm install
cd ..
```

Для локального запуска:

```bat
setup.bat
start.bat
```

## Проверки перед PR

```powershell
cd backend
python -m pytest -q
```

 frontend:

```powershell
cd frontend
npm run build
```

Ожидаемо: **132 passed**. E2E-тест `_final_e2e.py` требует запущенного сервера
на `http://127.0.0.1:8000` и даёт **78 проверок, 0 ошибок**.

## Правила кода

- Сохраняйте форматирование LLM: `format_number`/`format_percent` в `backend/app/utils.py`.
- Каждое новое число в ответе должно иметь источник (документ, страница, фрагмент).
- Не отправляйте полные PDF и полный текст в облако — только структурированные факты.
- Для изменений в OCR/таблицах добавляйте тесты в `backend/tests/test_ocr.py` / `test_extraction.py`.
- Не коммитьте `data/`, `.env`, `dist/`, `build/`, `.venv`, `node_modules` — они в `.gitignore`.

## Pull Request

1. Создайте ветку от `main`.
2. Внесите изменений и добавьте тесты.
3. Заполните [шаблон PR](.github/PULL_REQUEST_TEMPLATE.md).
4. Убедитесь, что CI зелёный (pytest + сборка frontend).

## Сообщения об ошибках

Используйте шаблон **Bug report**: укажите версию, ОС, шаги воспроизведения,
ожидаемый и фактический результат, лог из `%LOCALAPPDATA%\PDF Analyst\logs\desktop.log`
(для desktop-сборки). Не прикладывайте конфиденциальные PDF — замените их тестовыми.

## Безопасность

Уязвимости сообщайте приватно по адресу **vadiji.ai@gmail.com**, как описано в
[SECURITY.md](SECURITY.md). Не публикуйте их в публичных issue.
