import React from "react";
import { useProject } from "../state";

const FEATURES = [
  ["▤", "Извлечение PDF", "Текст, таблицы, числа, даты, единицы и периоды; OCR сканов на русском и английском."],
  ["✦", "AI-аналитик", "Локальный детерминированный движок, OpenAI-совместимые API и Ollama."],
  ["⇄", "Сравнение", "Нечёткое и межъязыковое сопоставление показателей, изменения и тренды."],
  ["◫", "Таблицы и графики", "7 типов таблиц и интерактивные графики Plotly с прозрачными формулами."],
  ["⌸", "Экспорт", "Excel, CSV, PDF-отчёты и PNG-графики."],
  ["ⓘ", "Источники", "Каждое число имеет ссылку на документ, страницу и фрагмент."],
];

export default function AboutPage() {
  const { health } = useProject();
  const about = health?.about;
  const version = about?.version || health?.version || "1.1.0";
  const author = about?.author || "VADIJI | AI Creative Studio";
  const email = about?.email || "vadiji.ai@gmail.com";
  const license = about?.license || "MIT";
  const copyright = about?.copyright || "© 2026 VADIJI | AI Creative Studio";

  return (
    <div className="mx-auto max-w-4xl space-y-5">
      <div>
        <h1 className="text-xl font-semibold text-slate-900">О программе</h1>
        <p className="text-sm text-slate-500">Сведения о приложении, версии и авторе.</p>
      </div>

      <section className="card overflow-hidden">
        <div className="flex flex-wrap items-center gap-4 border-b border-slate-100 p-6">
          <img
            src="/vadiji-logo.jpg"
            alt="VADIJI | AI Creative Studio"
            className="h-24 w-24 shrink-0 rounded-2xl object-cover ring-1 ring-lime-400/50"
          />
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="text-2xl font-semibold text-slate-900">{about?.name || "PDF Analyst"}</h2>
              <span className="chip bg-brand-50 text-brand-700">v{version}</span>
            </div>
            <p className="mt-1 text-sm text-slate-600">
              Локальное приложение для анализа, сравнения и экспорта данных из PDF-документов.
            </p>
          </div>
        </div>

        <div className="grid gap-4 p-6 md:grid-cols-2">
          <div className="rounded-xl bg-slate-50 p-4">
            <div className="text-[11px] font-medium uppercase tracking-wide text-slate-400">Автор</div>
            <div className="mt-1 text-sm font-semibold text-slate-900">{author}</div>
            <a className="link mt-1 inline-block text-sm" href={`mailto:${email}`}>
              {email}
            </a>
          </div>
          <div className="rounded-xl bg-slate-50 p-4">
            <div className="text-[11px] font-medium uppercase tracking-wide text-slate-400">Версия</div>
            <div className="mt-1 text-sm font-semibold tabular-nums text-slate-900">{version}</div>
            <div className="mt-1 text-xs text-slate-500">Windows 10/11 · локальный запуск</div>
          </div>
          <div className="rounded-xl bg-slate-50 p-4 md:col-span-2">
            <div className="text-[11px] font-medium uppercase tracking-wide text-slate-400">Лицензия</div>
            <div className="mt-1 flex flex-wrap items-center gap-2">
              <span className="chip bg-emerald-50 text-emerald-700">{license} License</span>
              <a className="link text-sm" href="/LICENSE.txt" target="_blank" rel="noreferrer">
                Текст лицензии
              </a>
            </div>
            <div className="mt-1 text-xs text-slate-500">{copyright}</div>
          </div>
        </div>
      </section>

      <section className="card p-6">
        <h3 className="text-sm font-semibold text-slate-900">Возможности</h3>
        <div className="mt-4 grid gap-3 sm:grid-cols-2">
          {FEATURES.map(([icon, title, text]) => (
            <div key={title} className="flex gap-3 rounded-xl border border-slate-100 p-3">
              <span className="text-lg leading-none text-brand-600">{icon}</span>
              <div>
                <div className="text-sm font-medium text-slate-800">{title}</div>
                <div className="mt-0.5 text-xs leading-5 text-slate-500">{text}</div>
              </div>
            </div>
          ))}
        </div>
      </section>

      <section className="card p-6">
        <h3 className="text-sm font-semibold text-slate-900">Техническая информация</h3>
        <dl className="mt-4 grid gap-x-8 gap-y-2 text-sm sm:grid-cols-2">
          <div className="flex justify-between gap-3 border-b border-slate-100 py-1.5">
            <dt className="text-slate-500">Версия</dt>
            <dd className="tabular-nums text-slate-800">{version}</dd>
          </div>
          <div className="flex justify-between gap-3 border-b border-slate-100 py-1.5">
            <dt className="text-slate-500">AI-провайдер</dt>
            <dd className="text-slate-800">{health?.ai?.provider || "—"}</dd>
          </div>
          <div className="flex justify-between gap-3 border-b border-slate-100 py-1.5">
            <dt className="text-slate-500">OCR (Tesseract)</dt>
            <dd className="text-slate-800">{health?.tesseract?.available ? "доступен" : "не найден"}</dd>
          </div>
          <div className="flex justify-between gap-3 border-b border-slate-100 py-1.5">
            <dt className="text-slate-500">Документов в базе</dt>
            <dd className="tabular-nums text-slate-800">{health?.documents ?? "—"}</dd>
          </div>
          <div className="flex justify-between gap-3 py-1.5 sm:col-span-2">
            <dt className="text-slate-500">Каталог данных</dt>
            <dd className="max-w-[70%] break-all text-right text-xs text-slate-700">
              {health?.data_dir || "—"}
            </dd>
          </div>
        </dl>
        <div className="mt-5 flex flex-wrap gap-2">
          <a className="btn-ghost" href="/api/docs" target="_blank" rel="noreferrer">
            API-документация
          </a>
          <a className="btn-ghost" href={`mailto:${email}?subject=PDF%20Analyst%20v${version}`}>
            Написать автору
          </a>
        </div>
      </section>

      <p className="text-center text-xs leading-5 text-slate-400">
        Все вычисления выполняются локально. Облачный AI (если включён) получает только найденные
        фрагменты, но не полные PDF. Приложение не заменяет аудиторскую проверку результатов.
      </p>
      <p className="text-center text-[11px] text-slate-400">
        {copyright} · Распространяется по лицензии {license}. Сторонние библиотеки имеют свои лицензии.
      </p>
    </div>
  );
}
