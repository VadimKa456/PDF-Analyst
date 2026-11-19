import React from "react";
import { api } from "../api";
import { useProject } from "../state";
import { AnswerCard, DataTable, EmptyState } from "../components/ui";
import type { AnalysisResult, Options } from "../types";

export default function ComparePage() {
  const { projectId, documents } = useProject();
  const ready = documents.filter((d) => d.status === "ready");
  const [selected, setSelected] = React.useState<number[]>([]);
  const [options, setOptions] = React.useState<Options | null>(null);
  const [labels, setLabels] = React.useState<string[]>([]);
  const [years, setYears] = React.useState<string[]>([]);
  const [result, setResult] = React.useState<AnalysisResult | null>(null);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState("");

  React.useEffect(() => {
    setSelected(ready.map((d) => d.id));
  }, [documents.filter((d) => d.status === "ready").map((d) => d.id).join(",")]);

  React.useEffect(() => {
    if (projectId == null) return;
    api
      .options(projectId)
      .then(setOptions)
      .catch(() => undefined);
  }, [projectId, documents.length]);

  const toggle = (list: string[], value: string) =>
    list.includes(value) ? list.filter((x) => x !== value) : [...list, value];

  const run = async () => {
    if (projectId == null || selected.length < 2) return;
    setLoading(true);
    setError("");
    try {
      const res = await api.compare({
        project_id: projectId,
        document_ids: selected,
        metric_labels: labels.length ? labels : undefined,
        years: years.length ? years : undefined,
        save: true,
      });
      setResult(res);
    } catch (e: any) {
      setError(e?.message || "Не удалось выполнить сравнение");
    } finally {
      setLoading(false);
    }
  };

  if (!projectId) {
    return <EmptyState title="Проект не выбран" text="Создайте проект и загрузите документы для сравнения." />;
  }

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-xl font-semibold text-slate-900">Сравнение документов</h1>
        <p className="text-sm text-slate-500">
          Сопоставление одинаковых показателей с разными названиями, расчёт абсолютного и процентного изменения,
          проверка совместимости единиц и поиск противоречий.
        </p>
      </div>

      <div className="card space-y-4 p-4">
        <div>
          <div className="label">Документы (минимум 2)</div>
          <div className="flex flex-wrap gap-2">
            {ready.map((d) => {
              const on = selected.includes(d.id);
              return (
                <button
                  key={d.id}
                  className={`chip border ${
                    on ? "border-brand-300 bg-brand-50 text-brand-700" : "border-slate-200 bg-white text-slate-600"
                  }`}
                  onClick={() =>
                    setSelected((prev) =>
                      prev.includes(d.id) ? prev.filter((x) => x !== d.id) : [...prev, d.id]
                    )
                  }
                >
                  {on ? "✓ " : ""}
                  {d.original_name}
                </button>
              );
            })}
            {!ready.length && <span className="text-sm text-slate-500">Нет готовых документов</span>}
          </div>
        </div>

        <div className="grid gap-4 md:grid-cols-2">
          <div>
            <div className="label">Показатели (необязательно)</div>
            <div className="scroll-thin flex max-h-40 flex-wrap gap-1 overflow-auto rounded-xl border border-slate-200 p-2">
              {(options?.labels || []).map((l) => (
                <button
                  key={l.normalized}
                  title={`встречается ${l.count} раз в ${l.document_count} документах`}
                  className={`chip border text-[11px] ${
                    labels.includes(l.label) ? "border-brand-300 bg-brand-50 text-brand-700" : "border-slate-200 bg-white"
                  }`}
                  onClick={() => setLabels((prev) => toggle(prev, l.label))}
                >
                  {l.label}
                </button>
              ))}
              {!options?.labels?.length && <span className="text-xs text-slate-400">Показатели появятся после обработки</span>}
            </div>
          </div>
          <div>
            <div className="label">Периоды (необязательно)</div>
            <div className="flex flex-wrap gap-1 rounded-xl border border-slate-200 p-2">
              {(options?.periods || []).map((p) => (
                <button
                  key={p}
                  className={`chip border text-[11px] ${
                    years.includes(p) ? "border-brand-300 bg-brand-50 text-brand-700" : "border-slate-200 bg-white"
                  }`}
                  onClick={() => setYears((prev) => toggle(prev, p))}
                >
                  {p}
                </button>
              ))}
              {!options?.periods?.length && <span className="text-xs text-slate-400">Периоды появятся после обработки</span>}
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <button className="btn-primary" disabled={selected.length < 2 || loading} onClick={() => void run()}>
            {loading ? "Сравнение…" : "Сравнить"}
          </button>
          <button
            className="btn-ghost"
            onClick={() => {
              setLabels([]);
              setYears([]);
            }}
          >
            Сбросить фильтры
          </button>
          <span className="text-xs text-slate-500">выбрано документов: {selected.length}</span>
        </div>
      </div>

      {error && <div className="rounded-xl bg-rose-50 px-4 py-3 text-sm text-rose-700">{error}</div>}

      {loading && <div className="card p-6 text-sm text-slate-500">Сопоставление показателей…</div>}

      {result && !loading && (
        <div className="space-y-4">
          <AnswerCard result={result} />
          {!!result.tables?.length &&
            result.tables.map((t, i) => <DataTable key={i} table={t} />)}
          {!!result.findings?.length && (
            <div className="card p-4">
              <div className="mb-2 text-sm font-semibold text-slate-900">Найденные расхождения</div>
              <ul className="space-y-1 text-sm text-slate-700">
                {result.findings.map((f, i) => (
                  <li key={i} className="flex gap-2">
                    <span className="text-rose-500">•</span>
                    {f.text}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
