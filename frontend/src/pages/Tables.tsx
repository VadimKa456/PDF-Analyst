import React from "react";
import { api } from "../api";
import { useProject } from "../state";
import { DataTable, EmptyState } from "../components/ui";
import type { Options, ResultTable } from "../types";

const TYPES = [
  ["summary", "Сводная"],
  ["comparison", "Сравнительная"],
  ["dynamics", "Динамика"],
  ["extrema", "Мин/макс"],
  ["missing", "Пропуски"],
  ["contradictions", "Противоречия"],
] as const;

export default function TablesPage() {
  const { projectId, documents } = useProject();
  const ready = documents.filter((d) => d.status === "ready");
  const [options, setOptions] = React.useState<Options | null>(null);
  const [type, setType] = React.useState<string>("summary");
  const [selected, setSelected] = React.useState<number[]>([]);
  const [labels, setLabels] = React.useState<string[]>([]);
  const [years, setYears] = React.useState<string[]>([]);
  const [search, setSearch] = React.useState("");
  const [tables, setTables] = React.useState<ResultTable[]>([]);
  const [warnings, setWarnings] = React.useState<string[]>([]);
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

  const toggle = (list: string[], v: string) =>
    list.includes(v) ? list.filter((x) => x !== v) : [...list, v];

  const build = async () => {
    if (projectId == null) return;
    setLoading(true);
    setError("");
    try {
      const res = await api.buildTable({
        project_id: projectId,
        type,
        document_ids: selected.length && selected.length !== ready.length ? selected : undefined,
        metric_labels: labels.length ? labels : undefined,
        years: years.length ? years : undefined,
        query: search,
      });
      setTables(res.tables || []);
      setWarnings(res.warnings || []);
    } catch (e: any) {
      setError(e?.message || "Не удалось построить таблицу");
    } finally {
      setLoading(false);
    }
  };

  if (!projectId) {
    return <EmptyState title="Проект не выбран" text="Создайте проект и загрузите документы." />;
  }

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-xl font-semibold text-slate-900">Таблицы</h1>
        <p className="text-sm text-slate-500">
          Сводные, сравнительные и аналитические таблицы по извлечённым показателям. Сортировка, фильтры и выбор
          столбцов доступны прямо в таблице.
        </p>
      </div>

      <div className="card space-y-4 p-4">
        <div className="grid gap-3 md:grid-cols-3">
          <div>
            <div className="label">Тип таблицы</div>
            <select className="input" value={type} onChange={(e) => setType(e.target.value)}>
              {TYPES.map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </div>
          <div>
            <div className="label">Поиск по названию показателя</div>
            <input
              className="input"
              placeholder="например: выручка"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
          <div>
            <div className="label">Документы</div>
            <div className="scroll-thin flex max-h-[72px] flex-wrap gap-1 overflow-auto rounded-xl border border-slate-200 p-1.5">
              {ready.map((d) => {
                const on = selected.includes(d.id);
                return (
                  <button
                    key={d.id}
                    className={`chip border text-[11px] ${
                      on ? "border-brand-300 bg-brand-50 text-brand-700" : "border-slate-200 bg-white"
                    }`}
                    onClick={() =>
                      setSelected((prev) => (on ? prev.filter((x) => x !== d.id) : [...prev, d.id]))
                    }
                  >
                    {d.original_name}
                  </button>
                );
              })}
              {!ready.length && <span className="text-xs text-slate-400">Нет готовых документов</span>}
            </div>
          </div>
        </div>

        <div className="grid gap-3 md:grid-cols-2">
          <div>
            <div className="label">Показатели (пусто — все)</div>
            <div className="scroll-thin flex max-h-32 flex-wrap gap-1 overflow-auto rounded-xl border border-slate-200 p-2">
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
            </div>
          </div>
          <div>
            <div className="label">Периоды (пусто — все)</div>
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
            </div>
          </div>
        </div>

        <button className="btn-primary" onClick={() => void build()} disabled={loading}>
          {loading ? "Построение…" : "Построить таблицу"}
        </button>
      </div>

      {error && <div className="rounded-xl bg-rose-50 px-4 py-3 text-sm text-rose-700">{error}</div>}
      {!!warnings.length && (
        <div className="rounded-xl bg-amber-50 px-4 py-3 text-xs text-amber-800">
          {warnings.map((w, i) => (
            <div key={i}>⚠ {w}</div>
          ))}
        </div>
      )}

      {loading && <div className="card p-6 text-sm text-slate-500">Расчёт таблицы…</div>}

      {!loading && !!tables.length && (
        <div className="space-y-4">
          {tables.map((t, i) => (
            <DataTable key={i} table={t} />
          ))}
        </div>
      )}

      {!loading && !tables.length && !error && (
        <div className="card p-8 text-center text-sm text-slate-500">
          Выберите параметры и нажмите «Построить таблицу».
        </div>
      )}
    </div>
  );
}
