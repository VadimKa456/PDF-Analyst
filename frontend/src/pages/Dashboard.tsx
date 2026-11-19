import React from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { useProject, useSource } from "../state";
import { ChartView, EmptyState, ProgressBar, StatusBadge } from "../components/ui";
import type { ChartConfig } from "../types";

function Stat({
  label,
  value,
  hint,
  accent,
}: {
  label: string;
  value: React.ReactNode;
  hint?: string;
  accent?: string;
}) {
  return (
    <div className="card px-4 py-3">
      <div className="text-[11px] font-medium uppercase tracking-wide text-slate-400">{label}</div>
      <div className={`mt-1 text-2xl font-semibold tabular-nums ${accent || "text-slate-900"}`}>{value}</div>
      {hint && <div className="mt-0.5 text-xs text-slate-500">{hint}</div>}
    </div>
  );
}

const fmt = (v: number | null | undefined, digits = 0) =>
  v == null
    ? "—"
    : Number(v).toLocaleString("ru-RU", {
        maximumFractionDigits: digits,
        minimumFractionDigits: 0,
      });

function scoreTone(score: number) {
  if (score >= 85) return { text: "text-emerald-600", bg: "bg-emerald-500", label: "отличное" };
  if (score >= 65) return { text: "text-amber-600", bg: "bg-amber-500", label: "удовлетворительное" };
  return { text: "text-rose-600", bg: "bg-rose-500", label: "требует проверки" };
}

function pieChart(id: string, title: string, labels: string[], values: number[]): ChartConfig {
  return {
    id,
    title,
    type: "pie",
    plotly: {
      data: [
        {
          type: "pie",
          labels,
          values,
          hole: 0.45,
          textinfo: "label+percent",
          hovertemplate: "%{label}: %{value}<extra></extra>",
        },
      ],
      layout: { title: { text: title }, margin: { l: 20, r: 20, t: 44, b: 20 }, showlegend: true },
    },
  };
}

function barChart(
  id: string,
  title: string,
  x: (string | number)[],
  y: number[],
  options: { horizontal?: boolean; color?: string; xTitle?: string; yTitle?: string } = {}
): ChartConfig {
  const horizontal = options.horizontal ?? false;
  return {
    id,
    title,
    type: "bar",
    plotly: {
      data: [
        horizontal
          ? {
              type: "bar",
              orientation: "h",
              x: y,
              y: x,
              marker: { color: options.color || "#2563eb" },
              hovertemplate: "%{y}: %{x}<extra></extra>",
            }
          : {
              type: "bar",
              x,
              y,
              marker: { color: options.color || "#2563eb" },
              hovertemplate: "%{x}: %{y}<extra></extra>",
            },
      ],
      layout: {
        title: { text: title },
        margin: horizontal ? { l: 220, r: 24, t: 44, b: 40 } : { l: 60, r: 24, t: 44, b: 60 },
        xaxis: { title: options.xTitle || "" },
        yaxis: { title: options.yTitle || "" },
      },
    },
  };
}

export default function DashboardPage() {
  const { projectId, project, documents, loading } = useProject();
  const { openSource } = useSource();
  const [data, setData] = React.useState<any>(null);
  const [error, setError] = React.useState("");

  React.useEffect(() => {
    if (projectId == null) return;
    let cancelled = false;
    api
      .dashboard(projectId)
      .then((res) => {
        if (!cancelled) {
          setData(res);
          setError("");
        }
      })
      .catch((e) => !cancelled && setError(e?.message || "Не удалось загрузить панель"));
    return () => {
      cancelled = true;
    };
  }, [projectId, documents.length, documents.filter((d) => d.status === "ready").length]);

  if (!projectId) {
    if (loading) return <div className="text-sm text-slate-500">Загрузка…</div>;
    return (
      <EmptyState
        title="Проект не выбран"
        text="Создайте проект в левой панели — в нём будут храниться документы, анализы и отчёты."
      />
    );
  }

  const stats = data?.stats || {};
  const quality = data?.quality || {};
  const coverage = data?.coverage || {};
  const topMetrics: any[] = data?.top_metrics || [];
  const periods: any[] = data?.periods || [];
  const latestValues: any[] = data?.latest_values || [];
  const attention: any[] = data?.needs_attention || [];
  const tone = scoreTone(quality.score || 0);

  const sourceData = coverage.metrics_by_source || {};
  const sourceLabels: string[] = [];
  const sourceValues: number[] = [];
  if (sourceData.table) {
    sourceLabels.push("Таблицы");
    sourceValues.push(sourceData.table);
  }
  if (sourceData.text) {
    sourceLabels.push("Текст");
    sourceValues.push(sourceData.text);
  }
  if (sourceData.other) {
    sourceLabels.push("Прочее");
    sourceValues.push(sourceData.other);
  }

  const docStats = (coverage.by_document || []).slice(0, 10);
  const charts: ChartConfig[] = [];
  if (sourceValues.length) {
    charts.push(pieChart("dash-source", "Откуда извлечены значения", sourceLabels, sourceValues));
  }
  if (periods.length) {
    charts.push(
      barChart(
        "dash-periods",
        "Покрытие по периодам",
        periods.map((p) => p.period),
        periods.map((p) => p.metrics),
        { color: "#0ea5e9", xTitle: "Период", yTitle: "Показателей" }
      )
    );
  }
  if (docStats.length) {
    charts.push(
      barChart(
        "dash-docs",
        "Показателей по документам",
        docStats.map((d: any) => d.name.length > 34 ? `${d.name.slice(0, 32)}…` : d.name),
        docStats.map((d: any) => d.metrics),
        { horizontal: true, color: "#7c3aed", xTitle: "Показателей" }
      )
    );
  }

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-slate-900">{project?.name || "Панель"}</h1>
          <p className="text-sm text-slate-500">
            Полная картина проекта: качество распознавания, покрытие данными, ключевые показатели и проблемные места.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Link to="/documents" className="btn-primary">
            Загрузить PDF
          </Link>
          <Link to="/analyst" className="btn-ghost">
            Задать вопрос
          </Link>
          <Link to="/compare" className="btn-ghost">
            Сравнить
          </Link>
        </div>
      </div>

      {error && <div className="rounded-xl bg-rose-50 px-4 py-3 text-sm text-rose-700">{error}</div>}

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
        <Stat
          label="Документы"
          value={stats.documents ?? documents.length}
          hint={`готово: ${stats.ready ?? 0} · ошибок: ${stats.errors ?? 0}`}
        />
        <Stat
          label="Страницы"
          value={stats.pages ?? 0}
          hint={`с текстом: ${stats.pages_with_text ?? 0} · OCR: ${stats.ocr_pages ?? 0}`}
        />
        <Stat
          label="Показатели"
          value={fmt(stats.metrics ?? 0)}
          hint={`таблиц: ${stats.tables ?? 0} · фрагментов: ${stats.chunks ?? 0}`}
        />
        <Stat
          label="Качество данных"
          value={`${quality.score ?? 0}/100`}
          hint={`средняя уверенность: ${Math.round((quality.avg_confidence || 0) * 100)}%`}
          accent={tone.text}
        />
        <Stat
          label="Анализы"
          value={stats.analyses ?? 0}
          hint={`сохранено: ${stats.saved_analyses ?? 0}`}
        />
      </div>

      {!!data?.processing?.length && (
        <div className="card p-4">
          <div className="mb-3 text-sm font-semibold text-slate-900">Идёт обработка</div>
          <div className="space-y-3">
            {data.processing.map((p: any) => (
              <div key={p.id}>
                <div className="mb-1 flex justify-between text-xs text-slate-600">
                  <span className="truncate">{p.name}</span>
                  <span>{p.progress}%</span>
                </div>
                <ProgressBar value={p.progress} />
                <div className="mt-1 text-[11px] text-slate-400">{p.stage}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-3">
        <div className="card p-4 lg:col-span-2">
          <div className="mb-3 flex items-center justify-between gap-2">
            <div>
              <div className="text-sm font-semibold text-slate-900">Качество распознавания</div>
              <div className="text-xs text-slate-500">
                OCR, уверенность и предупреждения по документам проекта
              </div>
            </div>
            <span className={`chip ${tone.text} bg-slate-100`}>{tone.label}</span>
          </div>

          <div className="mb-3 flex items-center gap-3">
            <div className="h-2.5 flex-1 overflow-hidden rounded-full bg-slate-100">
              <div className={`h-full ${tone.bg}`} style={{ width: `${quality.score || 0}%` }} />
            </div>
            <div className="w-14 text-right text-sm font-semibold tabular-nums text-slate-800">
              {quality.score ?? 0}%
            </div>
          </div>

          <div className="grid gap-2 sm:grid-cols-3">
            <div className="rounded-xl bg-slate-50 px-3 py-2">
              <div className="text-[11px] uppercase tracking-wide text-slate-400">Средняя уверенность</div>
              <div className="text-lg font-semibold tabular-nums text-slate-800">
                {Math.round((quality.avg_confidence || 0) * 100)}%
              </div>
            </div>
            <div className="rounded-xl bg-slate-50 px-3 py-2">
              <div className="text-[11px] uppercase tracking-wide text-slate-400">Документы с OCR</div>
              <div className="text-lg font-semibold tabular-nums text-slate-800">
                {quality.ocr_documents ?? 0} / {stats.documents ?? 0}
              </div>
            </div>
            <div className="rounded-xl bg-slate-50 px-3 py-2">
              <div className="text-[11px] uppercase tracking-wide text-slate-400">Предупреждения</div>
              <div
                className={`text-lg font-semibold tabular-nums ${
                  quality.warnings_count ? "text-amber-600" : "text-slate-800"
                }`}
              >
                {quality.warnings_count ?? 0}
              </div>
            </div>
          </div>

          {!!quality.low_confidence_documents?.length && (
            <div className="mt-3">
              <div className="mb-1 text-xs font-semibold text-slate-700">Низкая уверенность OCR</div>
              <ul className="divide-y divide-slate-100 rounded-xl border border-slate-200">
                {quality.low_confidence_documents.map((d: any) => (
                  <li key={d.id} className="flex items-center justify-between gap-3 px-3 py-2 text-xs">
                    <span className="truncate text-slate-700">{d.name}</span>
                    <span className="flex shrink-0 items-center gap-2 text-slate-500">
                      <span>{Math.round((d.confidence || 0) * 100)}%</span>
                      <Link to="/documents" className="link">
                        проверить
                      </Link>
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {!!quality.warnings?.length && (
            <details className="mt-3 rounded-xl bg-amber-50 px-3 py-2 text-xs text-amber-800">
              <summary className="cursor-pointer font-medium">
                Предупреждения ({quality.warnings_count})
              </summary>
              <ul className="mt-2 space-y-1">
                {quality.warnings.map((w: any, i: number) => (
                  <li key={i}>
                    <span className="font-medium">{w.name}:</span> {w.text}
                  </li>
                ))}
              </ul>
            </details>
          )}
        </div>

        <div className="card p-4">
          <div className="mb-3 text-sm font-semibold text-slate-900">Покрытие данными</div>
          <div className="space-y-3 text-sm">
            <div className="flex items-center justify-between">
              <span className="text-slate-600">Документы с показателями</span>
              <span className="font-semibold tabular-nums text-slate-900">
                {coverage.documents_with_metrics ?? 0} / {stats.ready ?? 0}
              </span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-slate-600">Документы с таблицами</span>
              <span className="font-semibold tabular-nums text-slate-900">
                {coverage.documents_with_tables ?? 0}
              </span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-slate-600">Значений из таблиц</span>
              <span className="font-semibold tabular-nums text-slate-900">
                {fmt(coverage.metrics_by_source?.table ?? 0)}
              </span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-slate-600">Значений из текста</span>
              <span className="font-semibold tabular-nums text-slate-900">
                {fmt(coverage.metrics_by_source?.text ?? 0)}
              </span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-slate-600">Страницы с текстом</span>
              <span className="font-semibold tabular-nums text-slate-900">
                {coverage.pages_with_text ?? 0} / {stats.pages ?? 0}
              </span>
            </div>
          </div>
          {!!coverage.documents_without_metrics?.length && (
            <div className="mt-3 rounded-xl bg-rose-50 px-3 py-2 text-xs text-rose-700">
              Без показателей:{" "}
              {coverage.documents_without_metrics.map((d: any) => d.name).join(", ")}
            </div>
          )}
        </div>
      </div>

      {!!charts.length && (
        <div className={`grid gap-4 ${charts.length > 1 ? "xl:grid-cols-2" : ""}`}>
          {charts.map((c) => (
            <ChartView key={c.id} chart={c} height={300} />
          ))}
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-3">
        <div className="card p-4 lg:col-span-2">
          <div className="mb-3 flex items-center justify-between">
            <div className="text-sm font-semibold text-slate-900">Ключевые показатели</div>
            <Link className="text-xs text-brand-600" to="/tables">
              все таблицы →
            </Link>
          </div>
          {!topMetrics.length ? (
            <div className="py-8 text-center text-sm text-slate-500">
              Показатели появятся после загрузки и обработки документов
            </div>
          ) : (
            <div className="scroll-thin max-h-[420px] overflow-auto">
              <table className="table-base">
                <thead className="sticky top-0">
                  <tr>
                    <th>Показатель</th>
                    <th>Докум.</th>
                    <th>Периоды</th>
                    <th className="text-right">Последнее значение</th>
                    <th>Источник</th>
                  </tr>
                </thead>
                <tbody>
                  {topMetrics.map((m: any) => (
                    <tr key={m.key}>
                      <td className="min-w-[200px]">{m.label}</td>
                      <td className="text-slate-600">{m.documents}</td>
                      <td className="text-slate-500">
                        {m.periods.length > 6
                          ? `${m.periods[0]} … ${m.periods[m.periods.length - 1]}`
                          : m.periods.join(", ") || "—"}
                      </td>
                      <td className="whitespace-nowrap text-right tabular-nums">
                        {m.latest ? `${fmt(m.latest.value, 2)} ${m.latest.unit || ""}` : "—"}
                      </td>
                      <td>
                        {m.latest ? (
                          <button
                            className="link truncate"
                            onClick={() =>
                              openSource({
                                document_id: m.latest.document_id,
                                document: m.latest.document,
                                page: m.latest.page,
                                metric_id: m.latest.metric_id,
                                value: String(m.latest.value ?? ""),
                                unit: m.latest.unit,
                                period: m.latest.period,
                              })
                            }
                          >
                            {m.latest.document} · стр. {m.latest.page}
                          </button>
                        ) : (
                          "—"
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        <div className="card p-4">
          <div className="mb-3 text-sm font-semibold text-slate-900">Требуют внимания</div>
          {!attention.length ? (
            <div className="py-8 text-center text-sm text-slate-500">Проблем не обнаружено</div>
          ) : (
            <ul className="divide-y divide-slate-100">
              {attention.map((d: any) => (
                <li key={d.id} className="py-2">
                  <div className="flex items-center justify-between gap-2">
                    <span className="truncate text-sm text-slate-800">{d.name}</span>
                    <StatusBadge status={d.status} />
                  </div>
                  <div className="mt-0.5 text-[11px] text-slate-500">{d.reasons.join(" · ")}</div>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <div className="card p-4">
          <div className="mb-3 flex items-center justify-between">
            <div className="text-sm font-semibold text-slate-900">Последние значения</div>
            <Link className="text-xs text-brand-600" to="/tables">
              к данным →
            </Link>
          </div>
          {!latestValues.length ? (
            <div className="py-8 text-center text-sm text-slate-500">Значений пока нет</div>
          ) : (
            <ul className="divide-y divide-slate-100">
              {latestValues.map((v: any) => (
                <li key={v.metric_id} className="flex items-center justify-between gap-3 py-2">
                  <div className="min-w-0">
                    <div className="truncate text-sm text-slate-800">{v.label}</div>
                    <div className="truncate text-[11px] text-slate-400">
                      {v.document} · стр. {v.page} {v.period ? `· ${v.period}` : ""}
                    </div>
                  </div>
                  <button
                    className="shrink-0 text-right text-sm font-medium tabular-nums text-brand-700"
                    onClick={() =>
                      openSource({
                        document_id: v.document_id,
                        document: v.document,
                        page: v.page,
                        metric_id: v.metric_id,
                        value: String(v.value ?? ""),
                        unit: v.unit,
                        period: v.period,
                      })
                    }
                  >
                    {fmt(v.value, 2)} {v.unit || ""}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="card p-4">
          <div className="mb-3 flex items-center justify-between">
            <div className="text-sm font-semibold text-slate-900">Последние анализы</div>
            <Link className="text-xs text-brand-600" to="/reports">
              все →
            </Link>
          </div>
          {!data?.recent_analyses?.length ? (
            <div className="py-8 text-center text-sm text-slate-500">Анализов пока нет</div>
          ) : (
            <ul className="divide-y divide-slate-100">
              {data.recent_analyses.map((a: any) => (
                <li key={a.id} className="py-2">
                  <Link to="/reports" className="block hover:bg-slate-50">
                    <div className="truncate text-sm font-medium text-slate-800">{a.title || a.query}</div>
                    <div className="flex gap-2 text-[11px] text-slate-400">
                      <span>{a.intent}</span>
                      <span>·</span>
                      <span>{a.created_at ? new Date(a.created_at).toLocaleString("ru-RU") : ""}</span>
                      {a.model && <span>· {a.model}</span>}
                    </div>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      <div className="grid gap-3 sm:grid-cols-3">
        {[
          { to: "/compare", title: "Сравнить документы", text: "Показатели по компаниям и периодам, изменения и противоречия." },
          { to: "/charts", title: "Построить график", text: "Динамика, структура, распределение — по реальным данным." },
          { to: "/reports", title: "Экспорт отчёта", text: "Excel, CSV и PDF с таблицами, графиками и источниками." },
        ].map((c) => (
          <Link key={c.to} to={c.to} className="card p-4 transition hover:border-brand-300 hover:shadow-md">
            <div className="text-sm font-semibold text-slate-900">{c.title}</div>
            <div className="mt-1 text-xs leading-5 text-slate-500">{c.text}</div>
          </Link>
        ))}
      </div>

      {!!data?.capabilities && !data.capabilities.ai_configured && (
        <div className="rounded-xl bg-amber-50 px-4 py-3 text-xs text-amber-800">
          AI-провайдер не настроен — работает локальный детерминированный аналитический движок. Это не ошибка:
          показатели, расчёты и сравнения выполняются без внешних моделей. Подключить OpenAI или Ollama можно в{" "}
          <Link className="link" to="/settings">
            настройках
          </Link>
          .
        </div>
      )}
    </div>
  );
}
