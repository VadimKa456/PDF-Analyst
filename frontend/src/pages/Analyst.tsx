import React from "react";
import { api } from "../api";
import { useProject } from "../state";
import { AnswerCard, CitationList, DataTable, EmptyState, ChartView } from "../components/ui";
import type { AnalysisResult } from "../types";

const EXAMPLES = [
  "Какая выручка у ООО «Альфа» в 2024 году?",
  "Сравни чистую прибыль компаний за 2023 год",
  "Покажи динамику выручки по годам",
  "У какой компании максимальные активы?",
  "Найди противоречия в документах",
  "Какие показатели отсутствуют за 2022 год?",
  "Покажи среднюю рентабельность",
  "Найди в тексте упоминание дивидендов",
];

export default function AnalystPage() {
  const { projectId, documents } = useProject();
  const [query, setQuery] = React.useState("");
  const [selected, setSelected] = React.useState<number[]>([]);
  const [result, setResult] = React.useState<AnalysisResult | null>(null);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState("");
  const [history, setHistory] = React.useState<any[]>([]);

  const ready = documents.filter((d) => d.status === "ready");

  React.useEffect(() => {
    setSelected(ready.map((d) => d.id));
  }, [documents.filter((d) => d.status === "ready").map((d) => d.id).join(",")]);

  const refreshHistory = React.useCallback(() => {
    if (projectId == null) return;
    api
      .analyses(projectId)
      .then((res) => setHistory(res.items))
      .catch(() => undefined);
  }, [projectId]);

  React.useEffect(refreshHistory, [refreshHistory]);

  const ask = async (text?: string) => {
    const q = (text ?? query).trim();
    if (!q || projectId == null) return;
    setLoading(true);
    setError("");
    try {
      const res = await api.analyze({
        project_id: projectId,
        query: q,
        document_ids: selected.length && selected.length !== ready.length ? selected : undefined,
      });
      setResult(res);
      if (text) setQuery(text);
      refreshHistory();
    } catch (e: any) {
      setError(e?.message || "Не удалось выполнить анализ");
    } finally {
      setLoading(false);
    }
  };

  const openHistory = async (id: number) => {
    try {
      const res = await api.analysis(id);
      setResult(res);
      setQuery(res.query || "");
    } catch (e: any) {
      setError(e?.message || "Не удалось открыть анализ");
    }
  };

  if (!projectId) {
    return <EmptyState title="Проект не выбран" text="Создайте проект и загрузите документы, чтобы задавать вопросы." />;
  }

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-xl font-semibold text-slate-900">AI-аналитик</h1>
        <p className="text-sm text-slate-500">
          Вопрос на естественном языке. Ответ строится на извлечённых данных, каждое число сопровождается источником.
        </p>
      </div>

      <div className="card p-4">
        <div className="label">Документы для анализа</div>
        <div className="mb-3 flex flex-wrap gap-2">
          {!ready.length && <span className="text-sm text-slate-500">Нет готовых документов</span>}
          {ready.map((d) => {
            const checked = selected.includes(d.id);
            return (
              <label
                key={d.id}
                className={`chip cursor-pointer border ${
                  checked ? "border-brand-300 bg-brand-50 text-brand-700" : "border-slate-200 bg-white text-slate-600"
                }`}
              >
                <input
                  type="checkbox"
                  className="hidden"
                  checked={checked}
                  onChange={() =>
                    setSelected((prev) => (checked ? prev.filter((x) => x !== d.id) : [...prev, d.id]))
                  }
                />
                {d.original_name}
              </label>
            );
          })}
        </div>
        <div className="flex flex-col gap-2 sm:flex-row">
          <textarea
            className="input min-h-[84px] flex-1 resize-y"
            placeholder="Например: сравните выручку компаний за 2022–2025 годы и покажите динамику"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) void ask();
            }}
          />
          <button className="btn-primary h-10 sm:self-end" disabled={loading || !query.trim()} onClick={() => void ask()}>
            {loading ? "Анализ…" : "Спросить"}
          </button>
        </div>
        <div className="mt-3 flex flex-wrap gap-1">
          {EXAMPLES.map((ex) => (
            <button
              key={ex}
              className="rounded-full border border-slate-200 px-2.5 py-1 text-[11px] text-slate-600 hover:border-brand-300 hover:text-brand-700"
              onClick={() => void ask(ex)}
            >
              {ex}
            </button>
          ))}
        </div>
      </div>

      {error && <div className="rounded-xl bg-rose-50 px-4 py-3 text-sm text-rose-700">{error}</div>}

      {loading && (
        <div className="card flex items-center gap-3 p-6 text-sm text-slate-500">
          <span className="h-4 w-4 animate-spin rounded-full border-2 border-brand-200 border-t-brand-600" />
          Поиск по документам и расчёт показателей…
        </div>
      )}

      {result && !loading && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <div className="text-sm text-slate-500">
              Запрос: <span className="text-slate-800">{result.query}</span>
            </div>
            <div className="text-xs text-slate-400">
              {result.meta?.duration_ms ? `${result.meta.duration_ms} мс` : ""}
            </div>
          </div>
          <AnswerCard result={result} />
          {!!result.tables?.length && result.tables.map((t, i) => <DataTable key={i} table={t} />)}
          {!!result.charts?.length && (
            <div className="grid gap-4 xl:grid-cols-2">
              {result.charts.map((c) => (
                <ChartView key={c.id} chart={c} />
              ))}
            </div>
          )}
          {!!result.citations?.length && <CitationList citations={result.citations} />}
        </div>
      )}

      <div className="card p-4">
        <div className="mb-3 flex items-center justify-between">
          <div className="text-sm font-semibold text-slate-900">История анализов</div>
          <span className="text-xs text-slate-400">{history.length}</span>
        </div>
        {!history.length ? (
          <div className="py-6 text-center text-sm text-slate-500">Анализов ещё нет</div>
        ) : (
          <ul className="divide-y divide-slate-100">
            {history.slice(0, 20).map((a) => (
              <li key={a.id} className="flex items-center justify-between gap-3 py-2">
                <button className="min-w-0 flex-1 text-left" onClick={() => void openHistory(a.id)}>
                  <div className="truncate text-sm text-slate-800">{a.title || a.query}</div>
                  <div className="text-[11px] text-slate-400">
                    {a.intent} · {a.created_at ? new Date(a.created_at).toLocaleString("ru-RU") : ""} · источников:{" "}
                    {a.sources_count ?? 0}
                  </div>
                </button>
                <button
                  className="btn-ghost px-2 py-1 text-xs"
                  onClick={() => void api.saveAnalysis(a.id, !a.saved).then(refreshHistory)}
                >
                  {a.saved ? "★" : "☆"}
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
