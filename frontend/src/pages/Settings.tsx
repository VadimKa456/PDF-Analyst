import React from "react";
import { api } from "../api";
import { useProject } from "../state";

type Tab = "ai" | "ocr" | "export" | "system";

export default function SettingsPage() {
  const { health } = useProject();
  const [tab, setTab] = React.useState<Tab>("ai");
  const [settings, setSettings] = React.useState<Record<string, any>>({});
  const [capabilities, setCapabilities] = React.useState<any>({});
  const [loading, setLoading] = React.useState(true);
  const [saving, setSaving] = React.useState(false);
  const [testing, setTesting] = React.useState(false);
  const [message, setMessage] = React.useState<{ type: "ok" | "err"; text: string } | null>(null);
  const [apiKey, setApiKey] = React.useState("");
  const [models, setModels] = React.useState<string[]>([]);
  const [modelFilter, setModelFilter] = React.useState("");
  const [embeddingTesting, setEmbeddingTesting] = React.useState(false);
  const modelsLoadedRef = React.useRef(false);

  const load = React.useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.getSettings();
      setSettings(res.settings || {});
      setCapabilities(res.capabilities || {});
    } catch (e: any) {
      setMessage({ type: "err", text: e?.message || "Не удалось загрузить настройки" });
    } finally {
      setLoading(false);
    }
  }, []);

  React.useEffect(() => {
    void load();
  }, [load]);

  const set = (key: string, value: any) => setSettings((prev) => ({ ...prev, [key]: value }));

  const save = async (extra: Record<string, any> = {}) => {
    setSaving(true);
    setMessage(null);
    try {
      const patch: Record<string, any> = {
        ai_provider: settings.ai_provider,
        openai_base_url: settings.openai_base_url,
        openai_model: settings.openai_model,
        openai_embedding_model: settings.openai_embedding_model,
        ollama_base_url: settings.ollama_base_url,
        ollama_model: settings.ollama_model,
        ollama_embedding_model: settings.ollama_embedding_model,
        ai_temperature: Number(settings.ai_temperature),
        ai_timeout_seconds: Number(settings.ai_timeout_seconds),
        semantic_search: !!settings.semantic_search,
        ocr_enabled: !!settings.ocr_enabled,
        ocr_languages: settings.ocr_languages,
        ocr_dpi: Number(settings.ocr_dpi),
        ocr_min_confidence: Number(settings.ocr_min_confidence),
        ocr_auto: !!settings.ocr_auto,
        tesseract_cmd: settings.tesseract_cmd,
        export_page_size: settings.export_page_size,
        export_include_sources: !!settings.export_include_sources,
        max_upload_mb: Number(settings.max_upload_mb),
        ...extra,
      };
      if (apiKey.trim()) patch.openai_api_key = apiKey.trim();
      const res = await api.updateSettings(patch);
      setSettings(res.settings || {});
      setCapabilities(res.capabilities || {});
      setApiKey("");
      setMessage({ type: "ok", text: "Настройки сохранены." });
      if ((patch.ai_provider || "none") !== "none") {
        modelsLoadedRef.current = false;
        void loadModels(true);
      }
    } catch (e: any) {
      setMessage({ type: "err", text: e?.message || "Не удалось сохранить настройки" });
    } finally {
      setSaving(false);
    }
  };

  const aiOverrides = React.useCallback(
    () => ({
      ai_provider: settings.ai_provider,
      openai_base_url: settings.openai_base_url,
      openai_model: settings.openai_model,
      openai_embedding_model: settings.openai_embedding_model,
      ollama_base_url: settings.ollama_base_url,
      ollama_model: settings.ollama_model,
      ollama_embedding_model: settings.ollama_embedding_model,
      ai_timeout_seconds: Number(settings.ai_timeout_seconds),
      ...(apiKey.trim() ? { openai_api_key: apiKey.trim() } : {}),
    }),
    [settings, apiKey]
  );

  const test = async () => {
    setTesting(true);
    setMessage(null);
    try {
      const res = await api.testAI(aiOverrides());
      if (res.ok) {
        setMessage({
          type: "ok",
          text: `Соединение работает${res.model ? `, модель: ${res.model}` : ""}${
            res.latency_ms ? `, ${res.latency_ms} мс` : ""
          }.`,
        });
      } else {
        if (Array.isArray(res.available_models) && res.available_models.length) {
          setModels(res.available_models);
          modelsLoadedRef.current = true;
        }
        setMessage({
          type: "err",
          text: [res.error || "AI-провайдер недоступен", res.hint].filter(Boolean).join("\n"),
        });
      }
    } catch (e: any) {
      setMessage({ type: "err", text: e?.message || "Ошибка проверки AI" });
    } finally {
      setTesting(false);
    }
  };

  const loadModels = React.useCallback(
    async (silent = false) => {
      try {
        const res = await api.aiModels(aiOverrides());
        const list: string[] = res.models || [];
        setModels(list);
        modelsLoadedRef.current = true;
        if (res.error) {
          if (!silent) setMessage({ type: "err", text: res.error });
        } else if (!silent) {
          setMessage({
            type: "ok",
            text: `Загружено моделей: ${list.length}. Нажмите на модель, чтобы выбрать её.`,
          });
        }
        return list;
      } catch (e: any) {
        if (!silent) {
          setMessage({ type: "err", text: e?.message || "Не удалось получить список моделей" });
        }
        return [] as string[];
      }
    },
    [aiOverrides]
  );

  const prevProviderRef = React.useRef(settings.ai_provider);
  React.useEffect(() => {
    if (prevProviderRef.current === settings.ai_provider) return;
    prevProviderRef.current = settings.ai_provider;
    setModels([]);
    setModelFilter("");
    modelsLoadedRef.current = false;
  }, [settings.ai_provider]);

  React.useEffect(() => {
    if (loading || modelsLoadedRef.current) return;
    if (settings.ai_provider === "none") return;
    if (settings.ai_provider === "openai" && !settings.openai_api_key_masked) return;
    void loadModels(true);
  }, [loading, settings.ai_provider, settings.openai_api_key_masked, loadModels]);

  const testEmbedding = async () => {
    setEmbeddingTesting(true);
    setMessage(null);
    try {
      const res = await api.testEmbedding(aiOverrides());
      setMessage(
        res.ok
          ? {
              type: "ok",
              text: `Модель эмбеддингов доступна: ${res.model}, размерность ${res.dimensions}.`,
            }
          : { type: "err", text: res.error || "Модель эмбеддингов недоступна" }
      );
    } catch (e: any) {
      setMessage({ type: "err", text: e?.message || "Ошибка проверки эмбеддингов" });
    } finally {
      setEmbeddingTesting(false);
    }
  };

  const checkOcr = async () => {
    try {
      const res = await api.checkOcr(settings.tesseract_cmd || "");
      setCapabilities((prev: any) => ({ ...prev, tesseract: res }));
      setMessage(
        res.available
          ? { type: "ok", text: `Tesseract доступен. Языки: ${(res.languages || []).join(", ")}` }
          : { type: "err", text: "Tesseract не найден. Укажите путь к tesseract.exe." }
      );
    } catch (e: any) {
      setMessage({ type: "err", text: e?.message || "Ошибка проверки OCR" });
    }
  };

  const provider = settings.ai_provider || "none";

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-xl font-semibold text-slate-900">Настройки</h1>
        <p className="text-sm text-slate-500">
          Локальный движок работает всегда. Внешний AI подключается только для формулировок и планирования, расчёты
          выполняются в Python.
        </p>
      </div>

      <div className="flex flex-wrap gap-1 border-b border-slate-200">
        {(
          [
            ["ai", "AI-провайдер"],
            ["ocr", "OCR"],
            ["export", "Экспорт"],
            ["system", "Система"],
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

      {message && (
        <div
          className={`rounded-xl px-4 py-3 text-sm whitespace-pre-line ${
            message.type === "ok" ? "bg-emerald-50 text-emerald-700" : "bg-rose-50 text-rose-700"
          }`}
        >
          {message.text}
        </div>
      )}

      {loading ? (
        <div className="card p-6 text-sm text-slate-500">Загрузка настроек…</div>
      ) : (
        <>
          {tab === "ai" && (
            <div className="card space-y-4 p-4">
              <div className="grid gap-3 md:grid-cols-3">
                {(
                  [
                    ["none", "Локальный движок", "Без внешних запросов. Детерминированные ответы, таблицы, расчёты."],
                    ["openai", "OpenAI / совместимый API", "Облако получает только найденные фрагменты, не PDF."],
                    ["ollama", "Ollama (локально)", "Локальная модель. Данные не покидают компьютер."],
                  ] as const
                ).map(([value, label, text]) => (
                  <button
                    key={value}
                    className={`rounded-xl border p-3 text-left transition ${
                      provider === value
                        ? "border-brand-400 bg-brand-50 ring-2 ring-brand-100"
                        : "border-slate-200 hover:border-slate-300"
                    }`}
                    onClick={() => set("ai_provider", value)}
                  >
                    <div className="text-sm font-semibold text-slate-900">{label}</div>
                    <div className="mt-1 text-xs leading-5 text-slate-500">{text}</div>
                  </button>
                ))}
              </div>

              {provider === "openai" && (
                <div className="grid gap-3 md:grid-cols-2">
                  <div>
                    <div className="label">Base URL</div>
                    <input
                      className="input"
                      value={settings.openai_base_url || ""}
                      onChange={(e) => set("openai_base_url", e.target.value)}
                      placeholder="https://api.openai.com/v1"
                    />
                    <p className="mt-1 text-xs text-slate-500">
                      Для удалённого провайдера нужен HTTPS. HTTP разрешён только для localhost.
                    </p>
                  </div>
                  <div>
                    <div className="label">API key {settings.openai_api_key_masked && `(сохранён: ${settings.openai_api_key_masked})`}</div>
                    <input
                      className="input"
                      type="password"
                      value={apiKey}
                      onChange={(e) => setApiKey(e.target.value)}
                      placeholder="sk-… (не отображается после сохранения)"
                    />
                  </div>
                  <div>
                    <div className="label">Модель</div>
                    <input
                      className="input"
                      list="openai-models"
                      value={settings.openai_model || ""}
                      onChange={(e) => set("openai_model", e.target.value)}
                      placeholder="gpt-4o-mini"
                    />
                    <datalist id="openai-models">
                      {models.map((m) => (
                        <option key={m} value={m} />
                      ))}
                    </datalist>
                    {models.length > 0 && settings.openai_model && !models.includes(String(settings.openai_model)) && (
                      <div className="mt-1 text-xs text-amber-700">
                        Модели «{settings.openai_model}» нет в списке провайдера — выберите доступную из подсказок.
                      </div>
                    )}
                  </div>
                  <div>
                    <div className="label">Модель эмбеддингов</div>
                    <input
                      className="input"
                      list="openai-embedding-models"
                      value={settings.openai_embedding_model || ""}
                      onChange={(e) => set("openai_embedding_model", e.target.value)}
                      placeholder="text-embedding-3-small"
                    />
                    <datalist id="openai-embedding-models">
                      {models.map((m) => (
                        <option key={m} value={m} />
                      ))}
                    </datalist>
                  </div>
                </div>
              )}

              {provider === "ollama" && (
                <div className="grid gap-3 md:grid-cols-2">
                  <div>
                    <div className="label">Base URL Ollama</div>
                    <input
                      className="input"
                      value={settings.ollama_base_url || ""}
                      onChange={(e) => set("ollama_base_url", e.target.value)}
                      placeholder="http://127.0.0.1:11434"
                    />
                    <p className="mt-1 text-xs text-slate-500">
                      HTTP разрешён только для localhost. Удалённый Ollama endpoint должен использовать HTTPS.
                    </p>
                  </div>
                  <div>
                    <div className="label">Модель</div>
                    <input
                      className="input"
                      list="ollama-models"
                      value={settings.ollama_model || ""}
                      onChange={(e) => set("ollama_model", e.target.value)}
                      placeholder="qwen2.5:7b"
                    />
                    <datalist id="ollama-models">
                      {models.map((m) => (
                        <option key={m} value={m} />
                      ))}
                    </datalist>
                  </div>
                  <div>
                    <div className="label">Модель эмбеддингов</div>
                    <input
                      className="input"
                      value={settings.ollama_embedding_model || ""}
                      onChange={(e) => set("ollama_embedding_model", e.target.value)}
                      placeholder="nomic-embed-text"
                    />
                  </div>
                </div>
              )}

              <div className="grid gap-3 md:grid-cols-3">
                <div>
                  <div className="label">Температура</div>
                  <input
                    className="input"
                    type="number"
                    min={0}
                    max={2}
                    step={0.1}
                    value={settings.ai_temperature ?? 0.2}
                    onChange={(e) => set("ai_temperature", e.target.value)}
                  />
                </div>
                <div>
                  <div className="label">Таймаут, сек</div>
                  <input
                    className="input"
                    type="number"
                    min={5}
                    max={900}
                    value={settings.ai_timeout_seconds ?? 60}
                    onChange={(e) => set("ai_timeout_seconds", e.target.value)}
                  />
                </div>
                <div className="flex flex-col justify-end gap-1 pb-1">
                  <label className="flex items-center gap-2 text-sm text-slate-600">
                    <input
                      type="checkbox"
                      checked={!!settings.semantic_search}
                      onChange={(e) => set("semantic_search", e.target.checked)}
                    />
                    семантический поиск (эмбеддинги)
                  </label>
                  <button
                    className="btn-ghost self-start px-2 py-1 text-xs"
                    disabled={embeddingTesting || provider === "none"}
                    onClick={() => void testEmbedding()}
                  >
                    {embeddingTesting ? "Проверка…" : "Проверить эмбеддинги"}
                  </button>
                </div>
              </div>

              <div className="flex flex-wrap gap-2">
                <button className="btn-primary" disabled={saving} onClick={() => void save()}>
                  {saving ? "Сохранение…" : "Сохранить"}
                </button>
                <button className="btn-ghost" disabled={testing || provider === "none"} onClick={() => void test()}>
                  {testing ? "Проверка…" : "Проверить соединение"}
                </button>
                <button className="btn-ghost" disabled={provider === "none"} onClick={() => void loadModels()}>
                  Список моделей
                </button>
              </div>
              {!!models.length && (
                <div className="space-y-2">
                  <input
                    className="input"
                    value={modelFilter}
                    onChange={(e) => setModelFilter(e.target.value)}
                    placeholder="Фильтр моделей, например glm или claude"
                  />
                  <div className="flex max-h-44 flex-wrap gap-1 overflow-y-auto">
                    {models
                      .filter((m) => m.toLowerCase().includes(modelFilter.trim().toLowerCase()))
                      .slice(0, 80)
                      .map((m) => (
                        <button
                          key={m}
                          className="chip border border-slate-200 bg-white font-mono text-[11px]"
                          onClick={() => set(provider === "ollama" ? "ollama_model" : "openai_model", m)}
                        >
                          {m}
                        </button>
                      ))}
                  </div>
                </div>
              )}
              <p className="text-xs text-slate-500">
                При включённом облачном AI в модель отправляются только найденные фрагменты и структурированные факты,
                необходимые для ответа. Полные PDF не передаются. Названия моделей у разных провайдеров отличаются:
                нажмите «Список моделей», чтобы увидеть доступные. Если модель эмбеддингов недоступна, семантический
                поиск автоматически использует лексический (FTS5) с предупреждением.
              </p>
            </div>
          )}

          {tab === "ocr" && (
            <div className="card space-y-4 p-4">
              <div className="grid gap-3 md:grid-cols-2">
                <div>
                  <div className="label">Путь к tesseract.exe (пусто — автопоиск)</div>
                  <input
                    className="input"
                    value={settings.tesseract_cmd || ""}
                    onChange={(e) => set("tesseract_cmd", e.target.value)}
                    placeholder="C:\Program Files\Tesseract-OCR\tesseract.exe"
                  />
                </div>
                <div>
                  <div className="label">Языки OCR</div>
                  <input
                    className="input"
                    value={settings.ocr_languages || ""}
                    onChange={(e) => set("ocr_languages", e.target.value)}
                    placeholder="rus+eng"
                  />
                </div>
                <div>
                  <div className="label">DPI рендеринга</div>
                  <input
                    className="input"
                    type="number"
                    min={150}
                    max={600}
                    value={settings.ocr_dpi ?? 300}
                    onChange={(e) => set("ocr_dpi", e.target.value)}
                  />
                </div>
                <div>
                  <div className="label">Минимальная уверенность, %</div>
                  <input
                    className="input"
                    type="number"
                    min={0}
                    max={100}
                    value={settings.ocr_min_confidence ?? 65}
                    onChange={(e) => set("ocr_min_confidence", e.target.value)}
                  />
                </div>
              </div>
              <div className="flex flex-wrap gap-4 text-sm text-slate-600">
                <label className="flex items-center gap-2">
                  <input type="checkbox" checked={!!settings.ocr_enabled} onChange={(e) => set("ocr_enabled", e.target.checked)} />
                  OCR включён
                </label>
                <label className="flex items-center gap-2">
                  <input type="checkbox" checked={!!settings.ocr_auto} onChange={(e) => set("ocr_auto", e.target.checked)} />
                  автоопределение сканированных страниц
                </label>
              </div>
              <div
                className={`rounded-xl px-4 py-3 text-xs ${
                  capabilities?.tesseract?.available
                    ? "bg-emerald-50 text-emerald-700"
                    : "bg-amber-50 text-amber-800"
                }`}
              >
                {capabilities?.tesseract?.available
                  ? `Tesseract найден: ${capabilities.tesseract.path}. Языки: ${(capabilities.tesseract.languages || []).join(", ")}`
                  : "Tesseract не найден — сканированные PDF не будут распознаны."}
              </div>
              <div className="flex gap-2">
                <button className="btn-primary" disabled={saving} onClick={() => void save()}>
                  Сохранить
                </button>
                <button className="btn-ghost" onClick={() => void checkOcr()}>
                  Проверить Tesseract
                </button>
              </div>
            </div>
          )}

          {tab === "export" && (
            <div className="card space-y-4 p-4">
              <div className="grid gap-3 md:grid-cols-2">
                <div>
                  <div className="label">Размер страницы PDF</div>
                  <select
                    className="input"
                    value={settings.export_page_size || "A4"}
                    onChange={(e) => set("export_page_size", e.target.value)}
                  >
                    <option value="A4">A4</option>
                    <option value="LETTER">Letter</option>
                  </select>
                </div>
                <div>
                  <div className="label">Максимальный размер загружаемого файла, МБ</div>
                  <input
                    className="input"
                    type="number"
                    min={1}
                    max={1000}
                    value={settings.max_upload_mb ?? 50}
                    onChange={(e) => set("max_upload_mb", e.target.value)}
                  />
                </div>
              </div>
              <label className="flex items-center gap-2 text-sm text-slate-600">
                <input
                  type="checkbox"
                  checked={!!settings.export_include_sources}
                  onChange={(e) => set("export_include_sources", e.target.checked)}
                />
                включать лист источников (документ, страница, фрагмент) в Excel и PDF
              </label>
              <button className="btn-primary" disabled={saving} onClick={() => void save()}>
                Сохранить
              </button>
            </div>
          )}

          {tab === "system" && (
            <div className="space-y-4">
              <div className="card grid gap-3 p-4 sm:grid-cols-2 lg:grid-cols-3">
                {[
                  ["Провайдер AI", provider],
                  ["AI настроен", capabilities?.ai_configured ? "да" : "нет"],
                  ["Документов", capabilities?.documents ?? 0],
                  ["Показателей", capabilities?.metrics ?? 0],
                  ["Фрагментов RAG", capabilities?.chunks ?? 0],
                  ["Размер БД", capabilities?.db_size ? `${(capabilities.db_size / 1024 / 1024).toFixed(2)} МБ` : "—"],
                  ["Папка данных", capabilities?.data_dir || "—"],
                  ["Фронтенд собран", capabilities?.frontend_built ? "да" : "нет"],
                  ["Tesseract", capabilities?.tesseract?.available ? "доступен" : "не найден"],
                ].map(([label, value]) => (
                  <div key={String(label)} className="rounded-xl bg-slate-50 p-3">
                    <div className="text-[11px] uppercase tracking-wide text-slate-400">{label}</div>
                    <div className="mt-1 break-words text-sm text-slate-800">{String(value)}</div>
                  </div>
                ))}
              </div>
              <div className="card p-4">
                <div className="text-sm font-semibold text-slate-900">Состояние</div>
                <ul className="mt-2 space-y-1 text-xs text-slate-600">
                  <li>• Версия API: {health?.version || "—"}</li>
                  <li>• Статус: {health?.status || "—"}</li>
                  <li>• Русский язык OCR: {health?.tesseract?.russian ? "да" : "нет"}</li>
                  <li>• Английский язык OCR: {health?.tesseract?.english ? "да" : "нет"}</li>
                </ul>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
