import React from "react";
import { api } from "../api";
import { useProject, useSource } from "../state";
import { DataTable, EmptyState, ProgressBar, StatusBadge, formatBytes } from "../components/ui";
import type { DocumentInfo, ResultTable } from "../types";

function MetricTable({ items }: { items: any[] }) {
  const { openSource } = useSource();
  if (!items.length) return <div className="py-6 text-center text-sm text-slate-500">Показатели не найдены</div>;
  return (
    <div className="scroll-thin max-h-[420px] overflow-auto">
      <table className="table-base">
        <thead className="sticky top-0">
          <tr>
            <th>Стр.</th>
            <th>Показатель</th>
            <th>Значение</th>
            <th>Период</th>
            <th>Ед.</th>
            <th>Источник</th>
          </tr>
        </thead>
        <tbody>
          {items.map((m) => (
            <tr key={m.id}>
              <td className="text-slate-500">{m.page}</td>
              <td className="min-w-[220px]">{m.label}</td>
              <td className="whitespace-nowrap tabular-nums">
                {m.value == null ? "—" : new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 4 }).format(m.value)}
              </td>
              <td>{m.period || "—"}</td>
              <td>{m.unit || "—"}</td>
              <td>
                <button
                  className="link text-xs"
                  onClick={() =>
                    openSource({
                      document_id: m.document_id,
                      document: m.document,
                      page: m.page,
                      snippet: m.context || m.raw_value,
                    })
                  }
                >
                  стр. {m.page}
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function DocumentDetail({ doc, onClose }: { doc: DocumentInfo; onClose: () => void }) {
  const [tab, setTab] = React.useState<"pages" | "metrics" | "tables" | "coverage">("pages");
  const [pages, setPages] = React.useState<any[]>([]);
  const [metrics, setMetrics] = React.useState<any[]>([]);
  const [tables, setTables] = React.useState<any[]>([]);
  const [coverage, setCoverage] = React.useState<any>(null);
  const [text, setText] = React.useState<{ page: number; text: string } | null>(null);
  const [loading, setLoading] = React.useState(false);
  const { openSource } = useSource();

  React.useEffect(() => {
    let cancelled = false;
    setLoading(true);
    Promise.all([
      api.documentPages(doc.id),
      api.documentMetrics(doc.id, 1000),
      api.documentTables(doc.id),
      api.documentCoverage(doc.id).catch(() => null),
    ])
      .then(([p, m, t, c]) => {
        if (cancelled) return;
        setPages(p);
        setMetrics(m.items.map((x: any) => ({ ...x, document_id: doc.id, document: doc.original_name })));
        setTables(t as any);
        setCoverage(c);
        setText(p.length ? null : null);
      })
      .catch(() => undefined)
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [doc.id]);

  const openPage = async (page: number) => {
    const res = await api.pageText(doc.id, page).catch(() => null);
    setText({ page, text: res?.text || "" });
  };

  const buildTable = (t: any): ResultTable => ({
    title: `${t.title || "Таблица"} · стр. ${t.page}`,
    columns: [
      { key: "c0", label: t.headers?.[0] || "Показатель", type: "string" },
      ...(t.headers || []).slice(1).map((h: string, i: number) => ({
        key: `c${i + 1}`,
        label: h || `Столбец ${i + 2}`,
        type: "string",
      })),
    ],
    rows: (t.rows || []).map((row: string[]) => {
      const obj: Record<string, any> = {};
      row.forEach((cell, i) => (obj[`c${i}`] = cell));
      return obj;
    }),
  });

  return (
    <div className="fixed inset-0 z-40 flex justify-end bg-slate-900/40" onClick={onClose}>
      <div
        className="flex h-full w-full max-w-5xl flex-col overflow-hidden bg-white shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-3 border-b border-slate-200 px-5 py-3">
          <div className="min-w-0">
            <div className="truncate text-base font-semibold text-slate-900">{doc.original_name}</div>
            <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-slate-500">
              <StatusBadge status={doc.status} />
              <span>{doc.page_count} стр.</span>
              <span>·</span>
              <span>{formatBytes(doc.size_bytes)}</span>
              <span>·</span>
              <span>показателей: {doc.metric_count}</span>
              <span>·</span>
              <span>таблиц: {doc.table_count}</span>
              {doc.ocr_used && <span className="chip bg-amber-50 text-amber-700">OCR {doc.ocr_pages} стр.</span>}
              {doc.avg_confidence > 0 && <span>точность: {Math.round(doc.avg_confidence * 100)}%</span>}
            </div>
          </div>
          <div className="flex shrink-0 gap-2">
            <a className="btn-ghost" href={api.fileUrl(doc.id)} target="_blank" rel="noreferrer">
              Открыть PDF
            </a>
            <button className="btn-ghost" onClick={onClose}>
              Закрыть
            </button>
          </div>
        </div>

        {doc.status === "error" && (
          <div className="mx-5 mt-4 rounded-xl bg-rose-50 px-4 py-3 text-sm text-rose-700">
            {doc.error || "Ошибка обработки"}
          </div>
        )}
        {!!doc.warnings?.length && (
          <div className="mx-5 mt-4 rounded-xl bg-amber-50 px-4 py-2 text-xs text-amber-800">
            {doc.warnings.map((w, i) => (
              <div key={i}>⚠ {w}</div>
            ))}
          </div>
        )}

        <div className="flex gap-1 border-b border-slate-200 px-5 pt-3">
          {(
            [
              ["pages", `Страницы (${pages.length})`],
              ["metrics", `Показатели (${metrics.length})`],
              ["tables", `Таблицы (${tables.length})`],
              ["coverage", "Покрытие чисел"],
            ] as const
          ).map(([key, label]) => (
            <button
              key={key}
              className={`rounded-t-lg px-3 py-2 text-sm ${
                tab === key ? "border-b-2 border-brand-600 font-medium text-brand-700" : "text-slate-500"
              }`}
              onClick={() => setTab(key)}
            >
              {label}
            </button>
          ))}
        </div>

        <div className="scroll-thin min-h-0 flex-1 overflow-auto p-5">
          {loading && <div className="text-sm text-slate-500">Загрузка данных документа…</div>}
          {!loading && tab === "pages" && (
            <div className="grid gap-4 lg:grid-cols-5">
              <div className="lg:col-span-2">
                <div className="space-y-2">
                  {pages.map((p) => (
                    <button
                      key={p.number}
                      onClick={() => openPage(p.number)}
                      className={`w-full rounded-xl border p-3 text-left text-xs transition ${
                        text?.page === p.number ? "border-brand-300 bg-brand-50" : "border-slate-200 hover:bg-slate-50"
                      }`}
                    >
                      <div className="flex items-center justify-between font-medium text-slate-800">
                        <span>Страница {p.number}</span>
                        <span className="text-[10px] uppercase text-slate-400">{p.method}</span>
                      </div>
                      <div className="mt-1 line-clamp-2 text-slate-500">{p.preview || "—"}</div>
                      <div className="mt-1 text-[10px] text-slate-400">
                        {p.chars} символов · точность {Math.round((p.confidence || 0) * 100)}%
                        {p.has_tables ? " · есть таблицы" : ""}
                      </div>
                    </button>
                  ))}
                  {!pages.length && <div className="text-sm text-slate-500">Страницы не найдены</div>}
                </div>
              </div>
              <div className="lg:col-span-3">
                {text ? (
                  <div className="space-y-2">
                    <div className="flex items-center justify-between">
                      <div className="label mb-0">Текст страницы {text.page}</div>
                      <button
                        className="link text-xs"
                        onClick={() =>
                          openSource({ document_id: doc.id, document: doc.original_name, page: text.page })
                        }
                      >
                        открыть источник
                      </button>
                    </div>
                    <pre className="scroll-thin max-h-[520px] overflow-auto whitespace-pre-wrap break-words rounded-xl bg-slate-50 p-4 text-sm leading-6 text-slate-700">
                      {text.text || "Текст недоступен"}
                    </pre>
                  </div>
                ) : (
                  <div className="rounded-xl border border-dashed border-slate-200 p-8 text-center text-sm text-slate-500">
                    Выберите страницу слева, чтобы посмотреть извлечённый текст.
                  </div>
                )}
              </div>
            </div>
          )}
          {!loading && tab === "metrics" && <MetricTable items={metrics} />}
          {!loading && tab === "tables" && (
            <div className="space-y-4">
              {!tables.length && <div className="text-sm text-slate-500">Таблицы не найдены</div>}
              {tables.map((t, i) => (
                <DataTable key={i} table={buildTable(t)} />
              ))}
            </div>
          )}
          {!loading && tab === "coverage" && (
            <div className="space-y-4">
              {!coverage ? (
                <div className="text-sm text-slate-500">Данные покрытия недоступны</div>
              ) : (
                <>
                  <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-5">
                    {[
                      ["Значимых чисел", coverage.summary.numbers],
                      ["Учтено в показателях", coverage.summary.matched],
                      ["Не сопоставлено", coverage.summary.unmatched],
                      [
                        "Покрытие",
                        `${Math.round((coverage.summary.match_rate || 0) * 100)}%`,
                      ],
                      ["Показателей", coverage.summary.metrics],
                    ].map(([label, value]) => (
                      <div key={String(label)} className="rounded-xl bg-slate-50 px-3 py-2">
                        <div className="text-[11px] uppercase tracking-wide text-slate-400">{label}</div>
                        <div className="text-lg font-semibold tabular-nums text-slate-800">{value}</div>
                      </div>
                    ))}
                  </div>
                  <div className="rounded-xl bg-slate-50 px-3 py-2 text-xs text-slate-600">
                    Значения из таблиц: <b>{coverage.summary.source_split.table}</b> · из текста:{" "}
                    <b>{coverage.summary.source_split.text}</b> · таблиц: <b>{coverage.summary.tables}</b> · OCR
                    страниц: <b>{coverage.summary.ocr_pages}</b>. Отдельно не учитываются служебные номера: коды
                    строк <b>{coverage.summary.service.codes}</b>, реквизиты{" "}
                    <b>{coverage.summary.service.requisites}</b>, даты{" "}
                    <b>{coverage.summary.service.dates}</b>, годы{" "}
                    <b>{coverage.summary.service.years}</b>. «Покрытие» считается только по значимым числам — так
                    видно, сколько реальных значений удалось привязать к показателям.
                  </div>
                  <div className="scroll-thin overflow-auto rounded-xl border border-slate-200">
                    <table className="table-base">
                      <thead className="sticky top-0">
                        <tr>
                          <th>Стр.</th>
                          <th>Метод</th>
                          <th>Символов</th>
                          <th>Показателей</th>
                          <th>Чисел</th>
                          <th>Учтено</th>
                          <th>Не сопоставлено</th>
                          <th>Служебные</th>
                        </tr>
                      </thead>
                      <tbody>
                        {coverage.pages.map((p: any) => (
                          <tr key={p.number}>
                            <td>
                              <button className="link" onClick={() => openPage(p.number)}>
                                {p.number}
                              </button>
                            </td>
                            <td>
                              <span className="chip bg-slate-100 text-slate-600">{p.method}</span>
                            </td>
                            <td className="tabular-nums">{p.chars}</td>
                            <td className="tabular-nums">{p.metrics}</td>
                            <td className="tabular-nums">{p.numbers}</td>
                            <td className="tabular-nums text-emerald-700">{p.matched}</td>
                            <td className="tabular-nums text-amber-700">{p.unmatched}</td>
                            <td className="tabular-nums text-slate-500">
                              {(p.service?.codes || 0) +
                                (p.service?.requisites || 0) +
                                (p.service?.dates || 0) +
                                (p.service?.years || 0)}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  {coverage.pages.map((p: any) =>
                    p.unmatched_examples?.length ? (
                      <div key={`u-${p.number}`} className="rounded-xl border border-slate-200 p-3">
                        <div className="mb-2 flex items-center justify-between">
                          <div className="text-xs font-semibold text-slate-700">
                            Страница {p.number}: числа без показателя ({p.unmatched})
                          </div>
                          <button className="link text-xs" onClick={() => openPage(p.number)}>
                            открыть текст
                          </button>
                        </div>
                        <div className="flex flex-wrap gap-1">
                          {p.unmatched_examples.map((n: any, i: number) => (
                            <span
                              key={i}
                              title={n.context}
                              className="chip border border-amber-200 bg-amber-50 text-[11px] text-amber-800"
                            >
                              {n.value}
                            </span>
                          ))}
                        </div>
                      </div>
                    ) : null
                  )}
                </>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default function DocumentsPage() {
  const {
    projectId,
    documents,
    uploading,
    uploadFiles,
    deleteDocument,
    reprocessDocument,
    loading,
  } = useProject();
  const [detail, setDetail] = React.useState<DocumentInfo | null>(null);
  const [drag, setDrag] = React.useState(false);
  const [busy, setBusy] = React.useState<number | null>(null);
  const inputRef = React.useRef<HTMLInputElement>(null);

  const pick = () => inputRef.current?.click();

  const onFiles = async (files: FileList | null) => {
    if (!files?.length) return;
    await uploadFiles(Array.from(files));
  };

  const onDelete = async (doc: DocumentInfo) => {
    if (!window.confirm(`Удалить «${doc.original_name}» и все извлечённые данные?`)) return;
    setBusy(doc.id);
    try {
      await deleteDocument(doc.id);
      if (detail?.id === doc.id) setDetail(null);
    } finally {
      setBusy(null);
    }
  };

  const onReprocess = async (doc: DocumentInfo) => {
    setBusy(doc.id);
    try {
      await reprocessDocument(doc.id);
    } finally {
      setBusy(null);
    }
  };

  if (!projectId) {
    return (
      <EmptyState
        title="Сначала создайте проект"
        text="Проект — это папка для документов. Создайте его в левой панели, затем загрузите PDF."
      />
    );
  }

  const ready = documents.filter((d) => d.status === "ready");
  const active = documents.filter((d) => d.status === "pending" || d.status === "processing");

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-xl font-semibold text-slate-900">Документы</h1>
        <p className="text-sm text-slate-500">
          Загрузите несколько PDF одновременно. Текст, таблицы и числа извлекаются автоматически; сканы распознаются OCR.
        </p>
      </div>

      <div
        className={`card flex flex-col items-center gap-3 border-dashed px-6 py-10 text-center transition ${
          drag ? "border-brand-400 bg-brand-50" : ""
        }`}
        onDragOver={(e) => {
          e.preventDefault();
          setDrag(true);
        }}
        onDragLeave={() => setDrag(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDrag(false);
          void onFiles(e.dataTransfer.files);
        }}
      >
        <div className="text-4xl">⇪</div>
        <div className="text-sm font-medium text-slate-800">Перетащите PDF сюда или выберите файлы</div>
        <div className="text-xs text-slate-500">
          Русский и английский языки · текстовые и сканированные документы · до 50 МБ на файл
        </div>
        <div className="flex gap-2">
          <button className="btn-primary" onClick={pick} disabled={uploading}>
            {uploading ? "Загрузка…" : "Выбрать PDF"}
          </button>
          <button className="btn-ghost" onClick={() => void onFiles(inputRef.current?.files || null)} disabled={uploading}>
            Повторить выбор
          </button>
        </div>
        <input
          ref={inputRef}
          type="file"
          accept="application/pdf,.pdf"
          multiple
          className="hidden"
          onChange={(e) => void onFiles(e.target.files)}
        />
      </div>

      {!!active.length && (
        <div className="card p-4">
          <div className="mb-2 text-sm font-semibold text-slate-900">Обработка ({active.length})</div>
          <div className="space-y-3">
            {active.map((d) => (
              <div key={d.id}>
                <div className="mb-1 flex justify-between text-xs text-slate-600">
                  <span className="truncate">{d.original_name}</span>
                  <span>{d.progress}%</span>
                </div>
                <ProgressBar value={d.progress} />
                <div className="mt-1 text-[11px] text-slate-400">{d.stage}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="card overflow-hidden">
        <div className="flex items-center justify-between border-b border-slate-200 px-4 py-3">
          <div className="text-sm font-semibold text-slate-900">
            Все документы ({documents.length}) · готово {ready.length}
          </div>
          <div className="text-xs text-slate-500">нажмите на строку, чтобы открыть данные</div>
        </div>
        {loading && !documents.length ? (
          <div className="p-8 text-center text-sm text-slate-500">Загрузка…</div>
        ) : !documents.length ? (
          <div className="p-10 text-center text-sm text-slate-500">В проекте пока нет документов</div>
        ) : (
          <div className="scroll-thin overflow-auto">
            <table className="table-base">
              <thead className="sticky top-0">
                <tr>
                  <th>Документ</th>
                  <th>Статус</th>
                  <th>Стр.</th>
                  <th>Показатели</th>
                  <th>Таблицы</th>
                  <th>OCR</th>
                  <th>Размер</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {documents.map((d) => (
                  <tr key={d.id} className="cursor-pointer hover:bg-slate-50" onClick={() => setDetail(d)}>
                    <td className="max-w-[320px]">
                      <div className="truncate font-medium text-slate-800">{d.original_name}</div>
                      <div className="text-[11px] text-slate-400">
                        {d.created_at ? new Date(d.created_at).toLocaleString("ru-RU") : ""}
                        {d.processing_ms ? ` · ${Math.round(d.processing_ms / 100) / 10} с` : ""}
                      </div>
                    </td>
                    <td>
                      <StatusBadge status={d.status} />
                      {d.status === "processing" && <div className="mt-1 text-[10px] text-slate-400">{d.progress}%</div>}
                    </td>
                    <td>{d.page_count}</td>
                    <td>{d.metric_count}</td>
                    <td>{d.table_count}</td>
                    <td>{d.ocr_pages ? `${d.ocr_pages} стр.` : "—"}</td>
                    <td className="whitespace-nowrap text-xs text-slate-500">{formatBytes(d.size_bytes)}</td>
                    <td onClick={(e) => e.stopPropagation()}>
                      <div className="flex justify-end gap-1">
                        <button
                          className="btn-ghost px-2 py-1 text-xs"
                          disabled={busy === d.id}
                          onClick={() => void onReprocess(d)}
                        >
                          Заново
                        </button>
                        <button
                          className="btn-danger px-2 py-1 text-xs"
                          disabled={busy === d.id}
                          onClick={() => void onDelete(d)}
                        >
                          Удалить
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {detail && <DocumentDetail doc={detail} onClose={() => setDetail(null)} />}
    </div>
  );
}
