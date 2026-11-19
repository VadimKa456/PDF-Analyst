import React from "react";
import { api } from "../api";
import { useProject } from "../state";
import { ChartView, EmptyState } from "../components/ui";
import type { ChartConfig, Options } from "../types";

const TYPES = [
  ["line", "Линейный"],
  ["bar", "Столбчатый"],
  ["stacked", "Накопительный"],
  ["pie", "Круговой"],
  ["scatter", "Точечный"],
  ["histogram", "Гистограмма"],
  ["heatmap", "Тепловая карта"],
] as const;

export default function ChartsPage() {
  const { projectId, documents } = useProject();
  const ready = documents.filter((d) => d.status === "ready");
  const [options, setOptions] = React.useState<Options | null>(null);
  const [type, setType] = React.useState<string>("line");
  const [xAxis, setXAxis] = React.useState("period");
  const [linked, setLinked] = React.useState(true);
  const [selected, setSelected] = React.useState<number[]>([]);
  const [labels, setLabels] = React.useState<string[]>([]);
  const [years, setYears] = React.useState<string[]>([]);
  const [title, setTitle] = React.useState("");
  const [search, setSearch] = React.useState("");
  const [charts, setCharts] = React.useState<ChartConfig[]>([]);
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
      const res = await api.buildChart({
        project_id: projectId,
        chart_type: type,
        x_axis: xAxis,
        document_ids: selected.length && selected.length !== ready.length ? selected : undefined,
        metric_labels: labels.length ? labels : undefined,
        years: years.length ? years : undefined,
        title,
        query: search,
      });
      setCharts(res.charts || []);
      setWarnings(res.warnings || []);
    } catch (e: any) {
      setError(e?.message || "Не удалось построить график");
    } finally {
      setLoading(false);
    }
  };

  const exportAll = async () => {
    for (const chart of charts) {
      await api.exportChartPng(chart).catch(() => undefined);
    }
  };

  if (!projectId) {
    return <EmptyState title="Проект не выбран" text="Создайте проект и загрузите документы." />;
  }

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-xl font-semibold text-slate-900">Графики</h1>
        <p className="text-sm text-slate-500">
          Визуализация извлечённых значений. Один запрос может построить несколько графиков — по одному на показатель
          или единицу измерения.
        </p>
      </div>

      <div className="card space-y-4 p-4">
        <div className="grid gap-3 md:grid-cols-4">
          <div>
            <div className="label">Тип графика</div>
            <select className="input" value={type} onChange={(e) => setType(e.target.value)}>
              {TYPES.map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </div>
          <div>
            <div className="label">Ось X</div>
            <select className="input" value={xAxis} onChange={(e) => setXAxis(e.target.value)}>
              <option value="period">Период</option>
              <option value="document">Документ</option>
              <option value="indicator">Показатель</option>
            </select>
          </div>
          <div>
            <div className="label">Заголовок</div>
            <input className="input" value={title} onChange={(e) => setTitle(e.target.value)} placeholder="необязательно" />
          </div>
          <label className="flex items-end gap-2 pb-2 text-xs text-slate-600">
            <input type="checkbox" checked={linked} onChange={(e) => setLinked(e.target.checked)} />
            несколько графиков на запрос
          </label>
        </div>

        <div>
          <div className="label">Документы</div>
          <div className="scroll-thin flex max-h-20 flex-wrap gap-1 overflow-auto rounded-xl border border-slate-200 p-2">
            {ready.map((d) => {
              const on = selected.includes(d.id);
              return (
                <button
                  key={d.id}
                  className={`chip border text-[11px] ${
                    on ? "border-brand-300 bg-brand-50 text-brand-700" : "border-slate-200 bg-white"
                  }`}
                  onClick={() => setSelected((prev) => (on ? prev.filter((x) => x !== d.id) : [...prev, d.id]))}
                >
                  {d.original_name}
                </button>
              );
            })}
            {!ready.length && <span className="text-xs text-slate-400">Нет готовых документов</span>}
          </div>
        </div>

        <div className="grid gap-3 md:grid-cols-2">
          <div>
            <div className="label">Показатели (пусто — подобрать по запросу)</div>
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
            <div className="label">Периоды</div>
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

        <div className="flex flex-wrap items-center gap-2">
          <input
            className="input h-10 max-w-xs"
            placeholder="Поиск по показателям, например: прибыль"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          <button className="btn-primary" onClick={() => void build()} disabled={loading}>
            {loading ? "Построение…" : "Построить графики"}
          </button>
          {!!charts.length && (
            <button className="btn-ghost" onClick={() => void exportAll()}>
              Скачать PNG ({charts.length})
            </button>
          )}
        </div>
      </div>

      {error && <div className="rounded-xl bg-rose-50 px-4 py-3 text-sm text-rose-700">{error}</div>}
      {!!warnings.length && (
        <div className="rounded-xl bg-amber-50 px-4 py-3 text-xs text-amber-800">
          {warnings.map((w, i) => (
            <div key={i}>⚠ {w}</div>
          ))}
        </div>
      )}

      {loading && <div className="card p-6 text-sm text-slate-500">Подготовка данных и построение графиков…</div>}

      {!loading && !!charts.length && (
        <div className={`grid gap-4 ${charts.length > 1 ? "xl:grid-cols-2" : ""}`}>
          {charts.map((c) => (
            <div key={c.id} className="space-y-2">
              <ChartView chart={c} />
              <div className="flex items-center justify-between text-xs text-slate-500">
                <span>
                  {c.title} {c.unit ? `· ${c.unit}` : ""}
                </span>
                <button className="link" onClick={() => void api.exportChartPng(c)}>
                  PNG
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {!loading && !charts.length && !error && (
        <div className="card p-8 text-center text-sm text-slate-500">
          Выберите показатели или введите запрос и нажмите «Построить графики».
        </div>
      )}
    </div>
  );
}
