import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { api } from "./api";
import type { DocumentInfo, HealthInfo, Project, SourceRef } from "./types";

interface ProjectState {
  projects: Project[];
  project: Project | null;
  projectId: number | null;
  documents: DocumentInfo[];
  health: HealthInfo | null;
  loading: boolean;
  uploading: boolean;
  error: string;
  refreshProjects: () => Promise<Project[]>;
  refreshDocuments: () => Promise<DocumentInfo[]>;
  selectProject: (id: number) => void;
  createProject: (name: string) => Promise<Project>;
  deleteProject: (id: number) => Promise<void>;
  uploadFiles: (files: File[]) => Promise<void>;
  deleteDocument: (id: number) => Promise<void>;
  reprocessDocument: (id: number) => Promise<void>;
}

const ProjectCtx = createContext<ProjectState | null>(null);
const STORAGE_KEY = "pdf-analyst-project";

export function ProjectProvider({ children }: { children: React.ReactNode }) {
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectId, setProjectId] = useState<number | null>(null);
  const [documents, setDocuments] = useState<DocumentInfo[]>([]);
  const [health, setHealth] = useState<HealthInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState("");

  const refreshProjects = useCallback(async () => {
    const list = await api.projects();
    setProjects(list);
    return list;
  }, []);

  const refreshDocuments = useCallback(async () => {
    if (projectId == null) return [];
    const docs = await api.documents(projectId);
    setDocuments(docs);
    return docs;
  }, [projectId]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      try {
        const [list, h] = await Promise.all([api.projects(), api.health().catch(() => null)]);
        if (cancelled) return;
        setProjects(list);
        if (h) setHealth(h);
        const stored = Number(localStorage.getItem(STORAGE_KEY));
        const preferred = list.find((p) => p.id === stored) || list[0];
        if (preferred) {
          setProjectId(preferred.id);
          localStorage.setItem(STORAGE_KEY, String(preferred.id));
        }
      } catch (e: any) {
        if (!cancelled) setError(e?.message || "Не удалось загрузить проекты");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (projectId == null) {
      setDocuments([]);
      return;
    }
    void api.openProject(projectId).catch(() => undefined);
    void refreshDocuments().catch((e) => setError(e?.message || "Не удалось загрузить документы"));
  }, [projectId, refreshDocuments]);

  const hasActive = documents.some((d) => d.status === "pending" || d.status === "processing");
  useEffect(() => {
    if (!hasActive || projectId == null) return;
    const timer = window.setInterval(() => {
      void refreshDocuments().catch(() => undefined);
    }, 1800);
    return () => window.clearInterval(timer);
  }, [hasActive, projectId, refreshDocuments]);

  // Обновляем счётчики проектов после завершения обработки
  useEffect(() => {
    if (!hasActive) void refreshProjects().catch(() => undefined);
  }, [hasActive, refreshProjects]);

  const selectProject = useCallback((id: number) => {
    setProjectId(id);
    localStorage.setItem(STORAGE_KEY, String(id));
  }, []);

  const createProject = useCallback(
    async (name: string) => {
      const p = await api.createProject(name);
      await refreshProjects();
      selectProject(p.id);
      return p;
    },
    [refreshProjects, selectProject]
  );

  const deleteProject = useCallback(
    async (id: number) => {
      setError("");
      try {
        await api.deleteProject(id);
      } catch (e: any) {
        setError(e?.message || "Не удалось удалить проект");
        throw e;
      }
      const list = await refreshProjects();
      if (id !== projectId) return;
      const next = list[0] || null;
      if (next) {
        selectProject(next.id);
      } else {
        setProjectId(null);
        localStorage.removeItem(STORAGE_KEY);
      }
    },
    [projectId, refreshProjects, selectProject]
  );

  const uploadFiles = useCallback(
    async (files: File[]) => {
      if (projectId == null) return;
      setUploading(true);
      setError("");
      try {
        const result = await api.upload(projectId, files);
        if (result.errors?.length) {
          setError(result.errors.map((e) => `${e.filename}: ${e.error}`).join("; "));
        }
        await refreshDocuments();
        await refreshProjects();
      } finally {
        setUploading(false);
      }
    },
    [projectId, refreshDocuments, refreshProjects]
  );

  const deleteDocument = useCallback(
    async (id: number) => {
      await api.deleteDocument(id);
      await refreshDocuments();
      await refreshProjects();
    },
    [refreshDocuments, refreshProjects]
  );

  const reprocessDocument = useCallback(
    async (id: number) => {
      await api.reprocessDocument(id);
      await refreshDocuments();
    },
    [refreshDocuments]
  );

  const project = useMemo(() => projects.find((p) => p.id === projectId) || null, [projects, projectId]);

  const value: ProjectState = {
    projects,
    project,
    projectId,
    documents,
    health,
    loading,
    uploading,
    error,
    refreshProjects,
    refreshDocuments,
    selectProject,
    createProject,
    deleteProject,
    uploadFiles,
    deleteDocument,
    reprocessDocument,
  };

  return <ProjectCtx.Provider value={value}>{children}</ProjectCtx.Provider>;
}

export function useProject() {
  const ctx = useContext(ProjectCtx);
  if (!ctx) throw new Error("useProject must be used inside ProjectProvider");
  return ctx;
}

interface SourceState {
  source: SourceRef | null;
  openSource: (source: SourceRef | null | undefined) => void;
}

const SourceCtx = createContext<SourceState | null>(null);

export function SourceProvider({ children }: { children: React.ReactNode }) {
  const [source, setSource] = useState<SourceRef | null>(null);
  return (
    <SourceCtx.Provider value={{ source, openSource: (s) => setSource(s || null) }}>
      {children}
      <SourceModal />
    </SourceCtx.Provider>
  );
}

export function useSource() {
  const ctx = useContext(SourceCtx);
  if (!ctx) throw new Error("useSource must be used inside SourceProvider");
  return ctx;
}

function SourceModal() {
  const { source, openSource } = useSource();
  const [text, setText] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!source) {
      setText("");
      return;
    }
    let cancelled = false;
    setLoading(true);
    api
      .pageText(source.document_id, source.page)
      .then((res) => {
        if (!cancelled) setText(res.text || "");
      })
      .catch(() => {
        if (!cancelled) setText("");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [source]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") openSource(null);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [openSource]);

  if (!source) return null;
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 p-4"
      onClick={() => openSource(null)}
    >
      <div
        className="card flex max-h-[92vh] w-full max-w-6xl flex-col overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-4 border-b border-slate-200 px-5 py-3">
          <div>
            <div className="text-sm font-semibold text-slate-900">
              {source.document || `Документ #${source.document_id}`} — стр. {source.page}
            </div>
            {source.snippet && (
              <div className="mt-1 max-w-3xl text-xs text-slate-500">{source.snippet}</div>
            )}
          </div>
          <div className="flex shrink-0 gap-2">
            <a
              className="btn-ghost"
              href={api.fileUrl(source.document_id, source.page)}
              target="_blank"
              rel="noreferrer"
            >
              Открыть PDF
            </a>
            <button className="btn-ghost" onClick={() => openSource(null)}>
              Закрыть
            </button>
          </div>
        </div>
        <div className="grid min-h-0 flex-1 gap-0 overflow-hidden md:grid-cols-2">
          <div className="scroll-thin overflow-auto border-r border-slate-200 bg-slate-100 p-3">
            <img
              className="mx-auto w-full max-w-2xl rounded-lg bg-white shadow"
              src={api.pageImageUrl(source.document_id, source.page)}
              alt={`Страница ${source.page}`}
            />
          </div>
          <div className="scroll-thin overflow-auto p-5">
            <div className="label">Текст страницы</div>
            {loading ? (
              <div className="text-sm text-slate-500">Загрузка…</div>
            ) : (
              <pre className="whitespace-pre-wrap break-words text-sm leading-6 text-slate-700">
                {text || "Текст страницы недоступен"}
              </pre>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
