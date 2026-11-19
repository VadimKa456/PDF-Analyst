export interface Project {
  id: number;
  name: string;
  description: string;
  created_at?: string;
  document_count: number;
  ready_count: number;
  page_count: number;
  analysis_count: number;
}

export interface DocumentInfo {
  id: number;
  project_id: number;
  original_name: string;
  filename: string;
  size_bytes: number;
  page_count: number;
  status: "pending" | "processing" | "ready" | "error";
  progress: number;
  stage: string;
  error: string;
  warnings: string[];
  ocr_used: boolean;
  ocr_pages: number;
  avg_confidence: number;
  text_chars: number;
  table_count: number;
  metric_count: number;
  chunk_count: number;
  processing_ms: number;
  created_at?: string;
  processed_at?: string;
}

export interface SourceRef {
  document_id: number;
  document?: string;
  page: number;
  snippet?: string;
  metric_id?: number;
  value?: string;
  unit?: string;
  period?: string;
}

export interface TableColumn {
  key: string;
  label: string;
  type: string;
}

export interface ResultTable {
  title: string;
  columns: TableColumn[];
  rows: Record<string, any>[];
  row_count?: number;
}

export interface ChartConfig {
  id: string;
  title: string;
  type: string;
  unit?: string;
  plotly: { data: any[]; layout: Record<string, any> };
}

export interface Citation {
  document_id: number;
  document?: string;
  page?: number;
  snippet?: string;
  metric_id?: number;
  value?: string;
  unit?: string;
  period?: string;
}

export interface AnalysisResult {
  id?: number;
  project_id?: number;
  title?: string;
  query: string;
  answer: string;
  intent?: string;
  tables?: ResultTable[];
  charts?: ChartConfig[];
  citations?: Citation[];
  documents?: { id: number; name: string }[];
  warnings?: string[];
  findings?: { text: string; type?: string; document_id?: number; page?: number }[];
  methods?: string[];
  meta?: Record<string, any>;
  saved?: boolean;
  created_at?: string;
}

export interface MetricLabel {
  normalized: string;
  label: string;
  count: number;
  document_count: number;
}

export interface Options {
  labels: MetricLabel[];
  periods: string[];
  units: string[];
  documents: { id: number; name: string; pages: number; status: string }[];
}

export interface HealthInfo {
  status: string;
  version: string;
  about?: { name: string; version: string; author: string; email: string; license?: string; copyright?: string };
  documents: number;
  tesseract: { available: boolean; path: string; languages: string[]; russian: boolean; english: boolean };
  ai: { provider: string; configured: boolean };
  data_dir: string;
}
