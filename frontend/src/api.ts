import type {
  AnalysisResult,
  DocumentInfo,
  HealthInfo,
  Options,
  Project,
  ResultTable,
} from "./types";

export class ApiError extends Error {
  status: number;
  constructor(message: string, status = 0) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api${path}`, {
    headers: init?.body instanceof FormData ? undefined : { "Content-Type": "application/json" },
    ...init,
  });
  if (!response.ok) {
    let message = `Ошибка ${response.status}`;
    try {
      const data = await response.json();
      message = data.detail || data.error || message;
      if (typeof message !== "string") message = JSON.stringify(message);
    } catch {
      // ignore
    }
    throw new ApiError(message, response.status);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export interface ExportResult {
  filename: string;
  savedPath: string;
  chosenPath: string;
  downloaded: boolean;
}

/** Завершает экспорт: в desktop-приложении — системный диалог сохранения,
 *  в браузере — обычное скачивание через blob. */
async function finishDownload(response: Response, fallbackName: string): Promise<ExportResult> {
  const disposition = response.headers.get("Content-Disposition") || "";
  const utfMatch = disposition.match(/filename\*=UTF-8''([^;]+)/i);
  const plainMatch = disposition.match(/filename="([^"]+)"/i);
  let filename = fallbackName;
  try {
    filename = decodeURIComponent(utfMatch?.[1] || plainMatch?.[1] || fallbackName);
  } catch {
    filename = utfMatch?.[1] || plainMatch?.[1] || fallbackName;
  }
  const savedHeader = response.headers.get("X-Saved-Path") || "";
  let savedPath = "";
  try {
    savedPath = savedHeader ? decodeURIComponent(savedHeader) : "";
  } catch {
    savedPath = savedHeader;
  }

  // В отдельном приложении (pywebview/WebView2) blob-скачивание не работает —
  // используем нативный диалог «Сохранить как» и копируем уже сохранённый сервером файл.
  const desktop = (window as any).pywebview?.api;
  if (desktop?.save_export && savedPath) {
    let chosenPath = "";
    try {
      chosenPath = (await desktop.save_export(savedPath, filename)) || "";
    } catch {
      chosenPath = "";
    }
    return { filename, savedPath, chosenPath, downloaded: false };
  }

  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.style.display = "none";
  document.body.appendChild(a);
  a.click();
  // Не отзываем URL сразу: Chromium/WebView2 могут отменить скачивание.
  window.setTimeout(() => {
    URL.revokeObjectURL(url);
    a.remove();
  }, 60000);
  return { filename, savedPath, chosenPath: "", downloaded: true };
}

export const api = {
  health: () => request<HealthInfo>("/health"),
  projects: () => request<Project[]>("/projects"),
  createProject: (name: string, description = "") =>
    request<Project>("/projects", { method: "POST", body: JSON.stringify({ name, description }) }),
  updateProject: (id: number, body: Partial<Project>) =>
    request<Project>(`/projects/${id}`, { method: "PUT", body: JSON.stringify(body) }),
  openProject: (id: number) => request<Project>(`/projects/${id}/open`, { method: "POST" }),
  deleteProject: (id: number) => request<{ ok: boolean }>(`/projects/${id}`, { method: "DELETE" }),

  documents: (projectId: number) => request<DocumentInfo[]>(`/projects/${projectId}/documents`),
  upload: async (projectId: number, files: File[]) => {
    const form = new FormData();
    files.forEach((f) => form.append("files", f));
    return request<{ documents: DocumentInfo[]; errors: { filename: string; error: string }[] }>(
      `/projects/${projectId}/documents`,
      { method: "POST", body: form }
    );
  },
  document: (id: number) => request<DocumentInfo>(`/documents/${id}`),
  deleteDocument: (id: number) => request<{ ok: boolean }>(`/documents/${id}`, { method: "DELETE" }),
  reprocessDocument: (id: number) =>
    request<{ ok: boolean }>(`/documents/${id}/reprocess`, { method: "POST" }),
  documentPages: (id: number) =>
    request<{ number: number; method: string; confidence: number; has_tables: boolean; chars: number; preview: string }[]>(
      `/documents/${id}/pages`
    ),
  pageText: (id: number, page: number) =>
    request<{ number: number; text: string; method: string; confidence: number; width: number; height: number }>(
      `/documents/${id}/pages/${page}`
    ),
  documentTables: (id: number) =>
    request<ResultTable[]>(`/documents/${id}/tables`),
  documentMetrics: (id: number, limit = 500) =>
    request<{ total: number; items: any[] }>(`/documents/${id}/metrics?limit=${limit}`),
  documentCoverage: (id: number) => request<any>(`/documents/${id}/coverage`),

  dashboard: (projectId?: number) =>
    request<any>(`/dashboard${projectId ? `?project_id=${projectId}` : ""}`),
  options: (projectId: number, documentIds?: number[]) => {
    const qs = documentIds?.length ? `&document_ids=${documentIds.join(",")}` : "";
    return request<Options>(`/options?project_id=${projectId}${qs}`);
  },

  analyze: (body: { project_id: number; query: string; document_ids?: number[]; metric_labels?: string[] }) =>
    request<AnalysisResult>("/analyses", { method: "POST", body: JSON.stringify(body) }),
  analyses: (projectId: number, savedOnly = false) =>
    request<{ total: number; items: any[] }>(
      `/analyses?project_id=${projectId}&saved_only=${savedOnly}`
    ),
  analysis: (id: number) => request<AnalysisResult>(`/analyses/${id}`),
  saveAnalysis: (id: number, saved = true) =>
    request<any>(`/analyses/${id}/saved?saved=${saved}`, { method: "PUT" }),
  deleteAnalysis: (id: number) => request<{ ok: boolean }>(`/analyses/${id}`, { method: "DELETE" }),
  rerunAnalysis: (id: number) => request<AnalysisResult>(`/analyses/${id}/rerun`, { method: "POST" }),

  compare: (body: {
    project_id: number;
    document_ids: number[];
    metric_labels?: string[];
    years?: string[];
    save?: boolean;
  }) => request<AnalysisResult>("/compare", { method: "POST", body: JSON.stringify(body) }),

  buildTable: (body: Record<string, any>) =>
    request<{ tables: ResultTable[]; warnings?: string[] }>("/tables/build", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  buildChart: (body: Record<string, any>) =>
    request<{ charts: any[]; warnings?: string[] }>("/charts/build", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  search: (body: { project_id: number; query: string; document_ids?: number[]; limit?: number }) =>
    request<any>("/search", { method: "POST", body: JSON.stringify(body) }),

  getSettings: () => request<any>("/settings"),
  updateSettings: (patch: Record<string, any>) =>
    request<any>("/settings", { method: "PUT", body: JSON.stringify(patch) }),
  testAI: (overrides: Record<string, any> = {}) =>
    request<any>("/settings/ai/test", { method: "POST", body: JSON.stringify(overrides) }),
  aiModels: (overrides: Record<string, any> = {}) =>
    request<any>("/settings/ai/models", { method: "POST", body: JSON.stringify(overrides) }),
  testEmbedding: (overrides: Record<string, any> = {}) =>
    request<any>("/settings/ai/embedding/test", { method: "POST", body: JSON.stringify(overrides) }),
  checkOcr: (tesseract_cmd = "") =>
    request<any>("/settings/ocr/check", {
      method: "POST",
      body: JSON.stringify({ tesseract_cmd }),
    }),

  exportFile: async (fmt: "xlsx" | "csv" | "pdf", payload: Record<string, any>) => {
    const response = await fetch(`/api/export/${fmt}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!response.ok) {
      let message = `Ошибка экспорта (${response.status})`;
      try {
        const data = await response.json();
        if (data.detail) message = data.detail;
      } catch {
        // ignore
      }
      throw new ApiError(message, response.status);
    }
    return finishDownload(response, `report.${fmt}`);
  },

  exportChartPng: async (chart: any) => {
    const response = await fetch("/api/export/chart-png", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ chart }),
    });
    if (!response.ok) throw new ApiError("Не удалось экспортировать график", response.status);
    return finishDownload(response, `${chart.title || "chart"}.png`);
  },

  fileUrl: (id: number, page?: number) =>
    `/api/documents/${id}/file${page ? `#page=${page}` : ""}`,
  pageImageUrl: (id: number, page: number) => `/api/documents/${id}/pages/${page}/image`,
};
