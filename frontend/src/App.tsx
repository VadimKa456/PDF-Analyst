import React, { useState } from "react";
import { NavLink, Navigate, Route, Routes, useLocation } from "react-router-dom";
import { ProjectProvider, SourceProvider, useProject } from "./state";
import DashboardPage from "./pages/Dashboard";
import DocumentsPage from "./pages/Documents";
import AnalystPage from "./pages/Analyst";
import ComparePage from "./pages/Compare";
import TablesPage from "./pages/Tables";
import ChartsPage from "./pages/Charts";
import ReportsPage from "./pages/Reports";
import SettingsPage from "./pages/Settings";
import AboutPage from "./pages/About";

const NAV = [
  { to: "/dashboard", label: "Панель", icon: "▦" },
  { to: "/documents", label: "Документы", icon: "▤" },
  { to: "/analyst", label: "AI-аналитик", icon: "✦" },
  { to: "/compare", label: "Сравнение", icon: "⇄" },
  { to: "/tables", label: "Таблицы", icon: "▥" },
  { to: "/charts", label: "Графики", icon: "◫" },
  { to: "/reports", label: "Отчёты", icon: "⌸" },
  { to: "/settings", label: "Настройки", icon: "⚙" },
  { to: "/about", label: "О программе", icon: "ⓘ" },
];

function ProjectBar() {
  const { projects, project, projectId, selectProject, createProject, deleteProject, health, error, loading } = useProject();
  const [creating, setCreating] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [name, setName] = useState("");

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;
    try {
      await createProject(name.trim());
      setName("");
      setCreating(false);
    } catch {
      // ошибка отображается в общем блоке
    }
  };

  const removeCurrent = async () => {
    if (projectId == null || !project || deleting) return;
    if (
      !window.confirm(
        `Удалить проект «${project.name}» и все его документы, показатели и отчёты? Это действие нельзя отменить.`
      )
    ) {
      return;
    }
    setDeleting(true);
    try {
      await deleteProject(projectId);
    } catch {
      // ошибка отображается в общем блоке state
    } finally {
      setDeleting(false);
    }
  };

  if (loading) {
    return <div className="px-4 py-2 text-xs text-slate-400">Загрузка проектов…</div>;
  }

  return (
    <div className="space-y-2 px-4">
      <div className="flex items-center gap-2">
        <select
          className="input h-9 flex-1 py-1"
          value={projectId ?? ""}
          onChange={(e) => selectProject(Number(e.target.value))}
          disabled={!projects.length}
        >
          {!projects.length && <option value="">Нет проектов</option>}
          {projects.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name} ({p.ready_count}/{p.document_count})
            </option>
          ))}
        </select>
        <button
          type="button"
          className="btn-ghost h-9 w-9 shrink-0 p-0"
          title="Новый проект"
          onClick={() => setCreating((v) => !v)}
        >
          +
        </button>
        <button
          type="button"
          className="btn-ghost h-9 w-9 shrink-0 p-0 text-rose-600 hover:bg-rose-50 disabled:opacity-40"
          title="Удалить текущий проект"
          disabled={!project || deleting}
          onClick={() => void removeCurrent()}
        >
          {deleting ? "…" : "×"}
        </button>
      </div>
      {creating && (
        <form onSubmit={submit} className="flex items-center gap-2">
          <input
            autoFocus
            className="input h-9 py-1"
            placeholder="Название проекта"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
          <button className="btn-primary h-9 py-1" type="submit">
            OK
          </button>
        </form>
      )}
      {error && <div className="rounded-lg bg-rose-50 px-2 py-1 text-xs text-rose-700">{error}</div>}
      {health && (
        <div className="flex flex-wrap gap-1 text-[10px] text-slate-400">
          <span className={`chip ${health.ai.configured ? "bg-emerald-50 text-emerald-700" : "bg-slate-100 text-slate-500"}`}>
            AI: {health.ai.provider}
          </span>
          <span className={`chip ${health.tesseract.available ? "bg-emerald-50 text-emerald-700" : "bg-amber-50 text-amber-700"}`}>
            OCR: {health.tesseract.available ? "готов" : "нет"}
          </span>
        </div>
      )}
    </div>
  );
}

function Shell({ children }: { children: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  const location = useLocation();
  return (
    <div className="flex min-h-screen bg-slate-50">
      <aside
        className={`fixed inset-y-0 left-0 z-40 w-64 transform border-r border-slate-200 bg-white transition-transform lg:static lg:translate-x-0 ${
          open ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        <div className="flex h-16 items-center gap-2 border-b border-slate-200 px-4">
          <div className="grid h-9 w-9 place-items-center rounded-xl bg-brand-600 text-white">π</div>
          <div>
            <div className="text-sm font-semibold leading-tight text-slate-900">PDF Analyst</div>
            <div className="text-[10px] uppercase tracking-wide text-slate-400">локальный анализ</div>
          </div>
        </div>
        <div className="border-b border-slate-100 py-3">
          <ProjectBar />
        </div>
        <nav className="space-y-1 p-3">
          {NAV.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              onClick={() => setOpen(false)}
              className={({ isActive }) =>
                `flex items-center gap-3 rounded-xl px-3 py-2 text-sm transition ${
                  isActive
                    ? "bg-brand-50 font-medium text-brand-700"
                    : "text-slate-600 hover:bg-slate-50 hover:text-slate-900"
                }`
              }
            >
              <span className="w-4 text-center text-base">{item.icon}</span>
              {item.label}
            </NavLink>
          ))}
        </nav>
        <div className="absolute bottom-0 w-full border-t border-slate-100 p-3 text-[10px] leading-4 text-slate-400">
          Все вычисления выполняются локально. Облачный AI получает только найденные фрагменты, не PDF целиком.
        </div>
      </aside>
      {open && (
        <div className="fixed inset-0 z-30 bg-slate-900/40 lg:hidden" onClick={() => setOpen(false)} />
      )}
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-20 flex h-16 items-center gap-3 border-b border-slate-200 bg-white/90 px-4 backdrop-blur lg:hidden">
          <button className="btn-ghost h-9 w-9 p-0" onClick={() => setOpen(true)}>
            ☰
          </button>
          <div className="text-sm font-semibold">{NAV.find((n) => location.pathname.startsWith(n.to))?.label || "PDF Analyst"}</div>
        </header>
        <main className="min-w-0 flex-1 p-4 md:p-6">{children}</main>
      </div>
    </div>
  );
}

export default function App() {
  return (
    <ProjectProvider>
      <SourceProvider>
        <Shell>
          <Routes>
            <Route path="/" element={<Navigate to="/dashboard" replace />} />
            <Route path="/dashboard" element={<DashboardPage />} />
            <Route path="/documents" element={<DocumentsPage />} />
            <Route path="/analyst" element={<AnalystPage />} />
            <Route path="/compare" element={<ComparePage />} />
            <Route path="/tables" element={<TablesPage />} />
            <Route path="/charts" element={<ChartsPage />} />
            <Route path="/reports" element={<ReportsPage />} />
            <Route path="/settings" element={<SettingsPage />} />
            <Route path="/about" element={<AboutPage />} />
            <Route path="*" element={<Navigate to="/dashboard" replace />} />
          </Routes>
        </Shell>
      </SourceProvider>
    </ProjectProvider>
  );
}
