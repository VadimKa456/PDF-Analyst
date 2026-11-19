import React from "react";
import { api } from "../api";
import { useProject } from "../state";
import { AnswerCard, CitationList, DataTable, EmptyState } from "../components/ui";
import type { AnalysisResult } from "../types";

export default function ReportsPage() {
  const { projectId, documents } = useProject();
  const ready = documents.filter((d) => d.status === "ready");
  const [savedOnly, setSavedOnly] = React.useState(false);
  const [items, setItems] = React.useState<any[]>([]);
  const [selected, setSelected] = React.useState<AnalysisResult | null>(null);
  const [loading, setLoading] = React.useState(false);
  const [exporting, setExporting] = React.useState("");
  const [error, setError] = React.useState("");
  const [notice, setNotice] = React.useState("");

  const load = React.useCallback(() => {
    if (projectId == null) return;
    api
      .analyses(projectId, savedOnly)
      .then((res) => setItems(res.items))
      .catch((e) => setError(e?.message || "Не удалось загрузить отчёты"));
  }, [projectId, savedOnly]);

  React.useEffect(load, [load]);

  const open = async (id: number) => {
    setLoading(true);
    setError("");
    try {
      const res = await api.analysis(id);
      setSelected(res);
    } catch (e: any) {
      setError(e?.message || "Не удалось открыть анализ");
    } finally {
      setLoading(false);
    }
  };

  const exportReport = async (fmt: "xlsx" | "csv" | "pdf", payload: Record<string, any>) => {
    setExporting(fmt);
    setError("");
    setNotice("");
    try {
      const result = await api.exportFile(fmt, payload);
      setNotice(
        result.chosenPath
          ? `Файл сохранён: ${result.chosenPath}`
          : result.savedPath
          ? `Файл сформирован и сохранён: ${result.savedPath}`
          : `Файл ${fmt.toUpperCase()} сформирован и скачан.`
      );
    } catch (e: any) {
      setError(e?.message || "Ошибка экспорта");
    } finally {
      setExporting("");
    }
  };

  const exportProject = async (fmt: "xlsx" | "csv" | "pdf") => {
    if (projectId == null || ready.length < 1) return;
    setExporting(fmt);
    setError("");
    setNotice("");
    try {
      // Реальный сводный отчёт: сравнение всех готовых документов + сформированные таблицы
      const compare =
        ready.length >= 2
          ? await api.compare({ project_id: projectId, document_ids: ready.map((d) => d.id), save: false })
          : null;
      const table = await api.buildTable({
        project_id: projectId,
        type: "summary",
        document_ids: ready.map((d) => d.id),
      });
      const result = await api.exportFile(fmt, {
        title: "Сводный отчёт по проекту",
        query: "Сводный отчёт по всем документам проекта",
        answer:
          compare?.answer ||
          "Сформирован сводный отчёт по показателям всех обработанных документов проекта.",
        tables: [...(compare?.tables || []), ...(table.tables || [])],
        charts: compare?.charts || [],
        citations: compare?.citations || [],
        documents: ready.map((d) => ({ id: d.id, name: d.original_name })),
        findings: compare?.findings || [],
        warnings: [...(compare?.warnings || []), ...(table.warnings || [])],
        methods: compare?.methods || [],
      });
      setNotice(
        result.chosenPath
          ? `Сводный отчёт сохранён: ${result.chosenPath}`
          : result.savedPath
          ? `Сводный отчёт сформирован и сохранён: ${result.savedPath}`
          : `Сводный отчёт ${fmt.toUpperCase()} сформирован и скачан.`
      );
    } catch (e: any) {
      setError(e?.message || "Ошибка формирования отчёта");
    } finally {
      setExporting("");
    }
  };

  if (!projectId) {
    return <EmptyState title="Проект не выбран" text="Создайте проект и загрузите документы." />;
  }

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-xl font-semibold text-slate-900">Отчёты</h1>
        <p className="text-sm text-slate-500">
          Экспорт анализов и сводных отчётов. Excel содержит таблицы и лист источников, PDF — таблицы, графики,
          выводы и ссылки на страницы.
        </p>
      </div>

      <div className="card space-y-3 p-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="text-sm font-semibold text-slate-900">Сводный отчёт по проекту</div>
          <div className="text-xs text-slate-500">готовых документов: {ready.length}</div>
        </div>
        <div className="flex flex-wrap gap-2">
          {(["xlsx", "csv", "pdf"] as const).map((fmt) => (
            <button
              key={fmt}
              className={fmt === "pdf" ? "btn-primary" : "btn-ghost"}
              disabled={!!exporting || !ready.length}
              onClick={() => void exportProject(fmt)}
            >
              {exporting === fmt ? "Формирование…" : fmt === "xlsx" ? "Excel (.xlsx)" : fmt === "csv" ? "CSV" : "PDF-отчёт"}
            </button>
          ))}
        </div>
        <p className="text-xs text-slate-500">
          Отчёт собирается по реальным извлечённым данным: сравнительная таблица, сводная таблица показателей и
          источники. Если документов меньше двух, сравнительная часть пропускается.
        </p>
      </div>

      {error && <div className="rounded-xl bg-rose-50 px-4 py-3 text-sm text-rose-700">{error}</div>}
      {notice && <div className="rounded-xl bg-emerald-50 px-4 py-3 text-sm text-emerald-700">{notice}</div>}

      <div className="grid gap-4 lg:grid-cols-3">
        <div className="card overflow-hidden lg:col-span-1">
          <div className="flex items-center justify-between border-b border-slate-200 px-4 py-3">
            <div className="text-sm font-semibold text-slate-900">Анализы</div>
            <label className="flex items-center gap-1 text-[11px] text-slate-500">
              <input type="checkbox" checked={savedOnly} onChange={(e) => setSavedOnly(e.target.checked)} />
              только избранные
            </label>
          </div>
          <div className="scroll-thin max-h-[520px] overflow-auto">
            {!items.length ? (
              <div className="p-6 text-center text-sm text-slate-500">
                Нет анализов. Задайте вопрос на странице «AI-аналитик».
              </div>
            ) : (
              <ul className="divide-y divide-slate-100">
                {items.map((a) => (
                  <li key={a.id} className="flex items-start gap-2 px-3 py-2">
                    <button className="min-w-0 flex-1 text-left" onClick={() => void open(a.id)}>
                      <div className="truncate text-sm text-slate-800">{a.title || a.query}</div>
                      <div className="text-[11px] text-slate-400">
                        {a.intent} · {a.created_at ? new Date(a.created_at).toLocaleDateString("ru-RU") : ""}
                      </div>
                    </button>
                    <button
                      className="text-slate-400 hover:text-amber-500"
                      title={a.saved ? "Убрать из избранного" : "Сохранить"}
                      onClick={() => void api.saveAnalysis(a.id, !a.saved).then(load)}
                    >
                      {a.saved ? "★" : "☆"}
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>

        <div className="space-y-4 lg:col-span-2">
          {loading && <div className="card p-6 text-sm text-slate-500">Загрузка анализа…</div>}
          {!selected && !loading && (
            <div className="card p-8 text-center text-sm text-slate-500">
              Выберите анализ слева, чтобы посмотреть и экспортировать его.
            </div>
          )}
          {selected && !loading && (
            <>
              <div className="card flex flex-wrap items-center justify-between gap-2 p-4">
                <div>
                  <div className="text-sm font-semibold text-slate-900">{selected.title || selected.query}</div>
                  <div className="text-xs text-slate-500">
                    {selected.created_at ? new Date(selected.created_at).toLocaleString("ru-RU") : ""}
                  </div>
                </div>
                <div className="flex flex-wrap gap-2">
                  {(["xlsx", "csv", "pdf"] as const).map((fmt) => (
                    <button
                      key={fmt}
                      className={fmt === "pdf" ? "btn-primary py-1.5" : "btn-ghost py-1.5"}
                      disabled={!!exporting}
                      onClick={() => void exportReport(fmt, { analysis_id: selected.id })}
                    >
                      {exporting === fmt ? "…" : fmt.toUpperCase()}
                    </button>
                  ))}
                </div>
              </div>
              <AnswerCard result={selected} />
              {!!selected.tables?.length && selected.tables.map((t, i) => <DataTable key={i} table={t} />)}
              {!!selected.citations?.length && <CitationList citations={selected.citations} />}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
