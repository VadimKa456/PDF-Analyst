import React, { useEffect, useMemo, useRef, useState } from "react";
import Plotly from "plotly.js-dist-min";
import { useSource } from "../state";
import type { AnalysisResult, ChartConfig, Citation, ResultTable, SourceRef } from "../types";

export function StatusBadge({ status }: { status: string }) {
  const map: Record<string, string> = {
    ready: "bg-emerald-50 text-emerald-700",
    processing: "bg-amber-50 text-amber-700",
    pending: "bg-slate-100 text-slate-600",
    error: "bg-rose-50 text-rose-700",
  };
  const labels: Record<string, string> = {
    ready: "Готов",
    processing: "Обработка",
    pending: "В очереди",
    error: "Ошибка",
  };
  return <span className={`chip ${map[status] || "bg-slate-100 text-slate-600"}`}>{labels[status] || status}</span>;
}

export function EmptyState({
  title,
  text,
  action,
}: {
  title: string;
  text: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="card flex flex-col items-center gap-3 px-6 py-12 text-center">
      <div className="text-lg font-semibold text-slate-900">{title}</div>
      <div className="max-w-xl text-sm text-slate-500">{text}</div>
      {action}
    </div>
  );
}

export function ProgressBar({ value }: { value: number }) {
  return (
    <div className="h-2 w-full overflow-hidden rounded-full bg-slate-100">
      <div
        className="h-full rounded-full bg-brand-600 transition-all"
        style={{ width: `${Math.max(2, Math.min(100, value))}%` }}
      />
    </div>
  );
}

function humanSize(bytes: number) {
  if (!bytes) return "0 Б";
  const units = ["Б", "КБ", "МБ", "ГБ"];
  const i = Math.min(units.length - 1, Math.floor(Math.log(bytes) / Math.log(1024)));
  return `${(bytes / Math.pow(1024, i)).toFixed(i ? 1 : 0)} ${units[i]}`;
}

export function formatBytes(bytes: number) {
  return humanSize(bytes);
}

export function DataTable({ table }: { table: ResultTable }) {
  const { openSource } = useSource();
  const [sortKey, setSortKey] = useState<string>("");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("asc");
  const [search, setSearch] = useState("");
  const [hidden, setHidden] = useState<Set<string>>(new Set());
  const [page, setPage] = useState(0);
  const pageSize = 50;

  const columns = table.columns || [];
  const rows = table.rows || [];
  const visibleColumns = columns.filter((c) => !hidden.has(c.key));

  const filtered = useMemo(() => {
    let list = rows;
    if (search.trim()) {
      const q = search.toLowerCase();
      list = list.filter((row) =>
        visibleColumns.some((c) => String(row[c.key] ?? "").toLowerCase().includes(q))
      );
    }
    if (sortKey) {
      list = [...list].sort((a, b) => {
        const av = a[sortKey];
        const bv = b[sortKey];
        const an = typeof av === "number" ? av : Number(String(av ?? "").replace(/\s/g, "").replace(",", "."));
        const bn = typeof bv === "number" ? bv : Number(String(bv ?? "").replace(/\s/g, "").replace(",", "."));
        let cmp: number;
        if (Number.isFinite(an) && Number.isFinite(bn) && String(av ?? "").trim() !== "" && String(bv ?? "").trim() !== "") {
          cmp = an - bn;
        } else {
          cmp = String(av ?? "").localeCompare(String(bv ?? ""), "ru");
        }
        return sortDir === "asc" ? cmp : -cmp;
      });
    }
    return list;
  }, [rows, search, sortKey, sortDir, visibleColumns]);

  useEffect(() => setPage(0), [search, sortKey, sortDir]);

  const totalPages = Math.max(1, Math.ceil(filtered.length / pageSize));
  const pageRows = filtered.slice(page * pageSize, page * pageSize + pageSize);

  const toggleSort = (key: string) => {
    if (sortKey === key) setSortDir(sortDir === "asc" ? "desc" : "asc");
    else {
      setSortKey(key);
      setSortDir("asc");
    }
  };

  const sourceFromRow = (row: Record<string, any>): SourceRef | null => {
    if (row.source && typeof row.source === "object" && row.source.document_id) return row.source as SourceRef;
    if (row.source_document_id && row.source_page) {
      return {
        document_id: row.source_document_id,
        document: row.source_document,
        page: row.source_page,
        snippet: row.source_snippet,
      };
    }
    return null;
  };

  const exportCsv = () => {
    const head = visibleColumns.map((c) => c.label);
    const formatCell = (row: Record<string, any>, c: (typeof visibleColumns)[number]) => {
      if (c.type === "source") return row.source_display || "";
      const value = row[c.key];
      if (c.type === "number" && typeof value === "number") {
        return new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 4 }).format(value);
      }
      return value ?? "";
    };
    const lines = filtered.map((row) =>
      visibleColumns
        .map((c) => `"${String(formatCell(row, c)).replace(/"/g, '""')}"`)
        .join(";")
    );
    const blob = new Blob(["\ufeff" + [head.join(";"), ...lines].join("\n")], {
      type: "text/csv;charset=utf-8",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${table.title || "table"}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="card overflow-hidden">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 px-4 py-3">
        <div>
          <div className="text-sm font-semibold text-slate-900">{table.title || "Таблица"}</div>
          <div className="text-xs text-slate-500">
            Строк: {filtered.length}
            {filtered.length !== rows.length ? ` из ${rows.length}` : ""} · столбцов: {visibleColumns.length}
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <input
            className="input h-9 w-48 py-1"
            placeholder="Поиск в таблице…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          <details className="relative">
            <summary className="btn-ghost h-9 cursor-pointer list-none py-1">Столбцы</summary>
            <div className="absolute right-0 z-20 mt-2 w-64 rounded-xl border border-slate-200 bg-white p-3 shadow-lg">
              {columns.map((c) => (
                <label key={c.key} className="flex items-center gap-2 py-1 text-sm">
                  <input
                    type="checkbox"
                    checked={!hidden.has(c.key)}
                    onChange={() => {
                      const next = new Set(hidden);
                      if (next.has(c.key)) next.delete(c.key);
                      else next.add(c.key);
                      setHidden(next);
                    }}
                  />
                  {c.label}
                </label>
              ))}
            </div>
          </details>
          <button className="btn-ghost h-9 py-1" onClick={exportCsv}>
            CSV
          </button>
        </div>
      </div>
      <div className="scroll-thin max-h-[560px] overflow-auto">
        <table className="table-base">
          <thead className="sticky top-0 z-10">
            <tr>
              {visibleColumns.map((c) => (
                <th key={c.key}>
                  <button className="inline-flex items-center gap-1" onClick={() => toggleSort(c.key)}>
                    {c.label}
                    <span className="text-[10px] text-slate-400">
                      {sortKey === c.key ? (sortDir === "asc" ? "▲" : "▼") : "↕"}
                    </span>
                  </button>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {pageRows.map((row, idx) => (
              <tr key={idx} className="hover:bg-slate-50/70">
                {visibleColumns.map((c) => {
                  if (c.type === "source") {
                    const source = sourceFromRow(row);
                    const label = row[c.key] || row.source_display || "Источник";
                    return (
                      <td key={c.key}>
                        {source ? (
                          <button className="link text-left" onClick={() => openSource(source)}>
                            {label}
                          </button>
                        ) : (
                          <span className="text-slate-400">—</span>
                        )}
                      </td>
                    );
                  }
                  if (c.type === "number" && typeof row[c.key] === "number") {
                    return (
                      <td key={c.key} className="whitespace-nowrap tabular-nums">
                        {new Intl.NumberFormat("ru-RU").format(row[c.key] as number)}
                      </td>
                    );
                  }
                  const value = row[c.key];
                  return (
                    <td key={c.key} className={c.key === "trend" ? trendClass(String(value ?? "")) : ""}>
                      {value === null || value === undefined || value === "" ? "—" : String(value)}
                    </td>
                  );
                })}
              </tr>
            ))}
            {pageRows.length === 0 && (
              <tr>
                <td className="px-4 py-8 text-center text-slate-500" colSpan={Math.max(1, visibleColumns.length)}>
                  Нет строк
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      {totalPages > 1 && (
        <div className="flex items-center justify-between border-t border-slate-200 px-4 py-2 text-sm">
          <span className="text-slate-500">
            Стр. {page + 1} из {totalPages}
          </span>
          <div className="flex gap-2">
            <button className="btn-ghost py-1" disabled={page === 0} onClick={() => setPage(page - 1)}>
              Назад
            </button>
            <button
              className="btn-ghost py-1"
              disabled={page + 1 >= totalPages}
              onClick={() => setPage(page + 1)}
            >
              Вперёд
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function trendClass(value: string) {
  const v = value.toLowerCase();
  if (v.includes("рост") || v.includes("↑")) return "text-emerald-600 font-medium";
  if (v.includes("сниж") || v.includes("↓")) return "text-rose-600 font-medium";
  return "";
}

export function ChartView({ chart, height = 420 }: { chart: ChartConfig; height?: number }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!ref.current || !chart?.plotly) return;
    const layout = {
      ...(chart.plotly.layout || {}),
      autosize: true,
      height,
      margin: chart.plotly.layout?.margin || { l: 60, r: 30, t: 40, b: 60 },
      font: { family: "Segoe UI, sans-serif", size: 12 },
    };
    Plotly.react(ref.current, chart.plotly.data || [], layout, {
      responsive: true,
      displayModeBar: true,
      displaylogo: false,
    });
    return () => {
      if (ref.current) Plotly.purge(ref.current);
    };
  }, [chart, height]);
  return (
    <div className="card overflow-hidden p-2">
      <div ref={ref} />
    </div>
  );
}

export function AnswerCard({ result }: { result: AnalysisResult }) {
  return (
    <div className="card p-5">
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <span className="chip bg-brand-50 text-brand-700">{result.intent || "анализ"}</span>
        {result.meta?.engine && (
          <span className="chip bg-slate-100 text-slate-600">движок: {String(result.meta.engine)}</span>
        )}
        {result.meta?.model && (
          <span className="chip bg-slate-100 text-slate-600">{String(result.meta.model)}</span>
        )}
      </div>
      <div className="whitespace-pre-wrap text-sm leading-6 text-slate-800">{result.answer}</div>
      {!!result.findings?.length && (
        <ul className="mt-3 space-y-1 text-sm text-slate-700">
          {result.findings.slice(0, 20).map((f, i) => (
            <li key={i} className="flex gap-2">
              <span className="text-brand-500">•</span>
              <span>{f.text}</span>
            </li>
          ))}
        </ul>
      )}
      {!!result.warnings?.length && (
        <div className="mt-4 rounded-xl bg-amber-50 p-3 text-xs text-amber-800">
          {result.warnings.map((w, i) => (
            <div key={i}>⚠ {w}</div>
          ))}
        </div>
      )}
      {!!result.methods?.length && (
        <details className="mt-4 text-xs text-slate-500">
          <summary className="cursor-pointer font-medium text-slate-600">Методика расчёта</summary>
          <ul className="mt-2 list-disc space-y-1 pl-5">
            {result.methods.map((m, i) => (
              <li key={i}>{m}</li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}

export function CitationList({ citations }: { citations: Citation[] }) {
  const { openSource } = useSource();
  if (!citations?.length) return null;
  return (
    <div className="card p-5">
      <div className="mb-3 text-sm font-semibold text-slate-900">Источники ({citations.length})</div>
      <div className="grid gap-2 md:grid-cols-2">
        {citations.map((c, i) => (
          <button
            key={i}
            className="rounded-xl border border-slate-200 bg-slate-50 p-3 text-left text-xs hover:border-brand-300 hover:bg-brand-50"
            onClick={() =>
              c.page != null
                ? openSource({
                    document_id: c.document_id,
                    document: c.document,
                    page: c.page,
                    snippet: c.snippet,
                  })
                : undefined
            }
          >
            <div className="font-medium text-slate-800">
              {c.document || `Документ #${c.document_id}`}, стр. {c.page}
            </div>
            {c.snippet && <div className="mt-1 line-clamp-2 text-slate-500">{c.snippet}</div>}
          </button>
        ))}
      </div>
    </div>
  );
}

export function ResultView({ result }: { result: AnalysisResult }) {
  return (
    <div className="space-y-4">
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
  );
}
