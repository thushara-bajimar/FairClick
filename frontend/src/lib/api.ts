// Typed client for the FairClick REST API (/api/*).

export interface TaskField { key: string; label: string; required: boolean; max: number; pattern?: string }
export interface TaskTypeMeta { id: string; title: string; objective: string; fields: TaskField[]; recommended_sites: string[] }
export interface SiteMeta { id: string; name: string; kind: string; patterns: string[]; url: string }
export interface TaxonomyItem { id: string; name: string; description: string; recommendation: string }
export interface Meta { task_types: TaskTypeMeta[]; sites: SiteMeta[]; taxonomy: TaxonomyItem[]; agent_mode: string }

export interface Task {
  id: string; task_type: string; task_title: string; site_id: string; site_name: string; status: string;
  inputs: Record<string, string>; created_at: string; completed_at: string | null; source: string;
  latest_session_id?: string | null; detection_count?: number;
}
export interface Session {
  id: string; task_id: string; status: string; status_detail: string | null; mode: string; current_url: string | null;
  current_step: number; live_screenshot_url: string | null; started_at: string; ended_at: string | null;
}
export interface AgentAction {
  id: string; step: number; agent: string; action_type: string; target: string | null; detail: string | null;
  page_url: string | null; risk: string | null; outcome: string | null; timestamp: string;
}
export interface Detection {
  id: string; category: string; pattern_name: string; description: string; evidence_text: string; location: string;
  severity: string; confidence: number; recommendation: string; page_url: string; page_path: string; timestamp: string;
  screenshot_url: string | null;
}
export interface Approval {
  id: string; session_id: string; action_summary: string; reason: string; consequences: string; target_label: string;
  page_url: string; status: string; created_at: string; screenshot_url: string | null;
  data: { fields: { label: string; value: string }[]; hidden_fields_set_by_website?: { name: string; value: string }[] };
  decision?: string | null; decided_by?: string | null; decided_at?: string | null; task_type?: string; site_id?: string;
}
export interface Incident { id: string; kind: string; description: string; evidence_text: string; page_url: string; action_taken: string; timestamp: string }
export interface TaskResult {
  outcome: string; success: number; summary: string; reference: string | null; prepared_document: string | null;
  interactions: number; pages_visited: number; duration_seconds: number; patterns_detected: number; evidence_count: number;
  approvals_requested: number;
}
export interface SessionDetail {
  session: Session; task: Task; actions: AgentAction[]; detections: Detection[]; approvals: Approval[];
  incidents: Incident[]; result: TaskResult | null;
}
export interface EvidenceRecord {
  id: string; session_id: string; task_id: string; site_id: string; site_name: string; task_type: string; category: string;
  pattern_name: string; severity: string; description: string; evidence_text: string; location: string; recommendation: string;
  screenshot_url: string | null; page_url: string; timestamp: string; confidence: number;
  supporting: Record<string, unknown>;
}
export interface Summary {
  total_tasks: number; completed_tasks: number; failed_tasks: number; rejected_tasks: number; running_tasks: number;
  attempted_runs: number; successful_runs: number; success_rate: number | null; patterns_detected: number;
  evidence_records: number; average_completion_seconds: number | null; total_interactions: number;
  average_interactions: number | null; security_incidents: number;
  approvals: { total: number; pending: number; approved: number; rejected: number };
  by_category: { category: string; name: string; count: number }[];
  by_site: { site_id: string; name: string; count: number }[];
  by_task: { task_type: string; title: string; attempted: number; succeeded: number; avg_duration: number }[];
  per_day: { day: string; tasks: number; succeeded: number }[];
  recent_activity: { timestamp: string; agent: string; action_type: string; target: string; outcome: string; session_id: string; task_type: string; site_id: string }[];
}
export interface BenchmarkRun {
  session_id: string; outcome: string; success: boolean; interactions: number; duration_s: number; pages: number;
  detections: number; evidence: number; approvals: number; security_incidents: number;
  score: { expected: number; true_positives: number; false_positives: number; false_negatives: number; missed: string[]; extra: string[] };
}
export interface BenchmarkScenario {
  scenario: string; task_type: string; site_id: string;
  manual: { success: boolean; interactions: number; pages: number; obstacles_encountered: number; estimated_time_s: number; time_is_estimate: boolean };
  agent_runs: BenchmarkRun[];
  agent_summary: { success_rate: number; avg_interactions: number; avg_duration_s: number; avg_detections: number; approvals: number };
}
export interface Benchmark {
  available: boolean;
  summary?: {
    generated_at: string; repeats: number; scenarios: number; agent_runs: number; agent_success_rate: number;
    detection_rate: number | null; detection_precision: number | null; true_positives: number; false_positives: number;
    false_negatives: number; agent_avg_duration_s: number | null; agent_avg_interactions: number | null;
    manual_success_rate: number; manual_avg_interactions: number; manual_avg_estimated_time_s: number;
    total_approvals_requested: number; total_evidence: number; total_security_incidents: number; notes: string[];
  };
  scenarios?: BenchmarkScenario[];
}
export interface SettingsResponse {
  preferences: {
    display_name: string; require_approval_for_consent: boolean; capture_screenshots: boolean; headless_browser: boolean;
    step_delay_ms: number; retain_history_days: number; store_page_text: boolean;
  };
  server: { agent_mode: string; llm_provider: string; llm_key_configured: boolean; max_steps: number; approval_timeout_s: number; allowed_navigation: string };
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, { headers: { 'Content-Type': 'application/json' }, ...init });
  if (!response.ok) {
    let message = `${response.status} ${response.statusText}`;
    try {
      const body = await response.json();
      if (typeof body.detail === 'string') message = body.detail;
      else if (Array.isArray(body.detail)) message = body.detail.map((d: { msg: string }) => d.msg.replace(/^Value error, /, '')).join('; ');
    } catch { /* not JSON */ }
    throw new ApiError(response.status, message);
  }
  return response.json() as Promise<T>;
}

export const api = {
  meta: () => request<Meta>('/api/meta'),
  summary: () => request<Summary>('/api/analytics/summary'),
  benchmark: () => request<Benchmark>('/api/analytics/benchmark'),
  tasks: (limit = 50) => request<Task[]>(`/api/tasks?limit=${limit}`),
  createTask: (body: { task_type: string; site_id: string; inputs: Record<string, string> }) =>
    request<{ task_id: string; session_id: string }>('/api/tasks', { method: 'POST', body: JSON.stringify(body) }),
  rerunTask: (taskId: string) => request<{ task_id: string; session_id: string }>(`/api/tasks/${taskId}/run`, { method: 'POST' }),
  session: (id: string) => request<SessionDetail>(`/api/sessions/${id}`),
  stopSession: (id: string) => request<{ stopping: boolean }>(`/api/sessions/${id}/stop`, { method: 'POST' }),
  approvals: (status?: string) => request<Approval[]>(`/api/approvals${status ? `?status=${status}` : ''}`),
  decide: (id: string, approved: boolean, comment = '') =>
    request<{ decision: string }>(`/api/approvals/${id}/decision`, { method: 'POST', body: JSON.stringify({ approved, comment, decided_by: 'user' }) }),
  evidence: (params: { category?: string; site_id?: string; task_id?: string } = {}) => {
    const qs = new URLSearchParams(Object.entries(params).filter(([, v]) => v) as [string, string][]).toString();
    return request<EvidenceRecord[]>(`/api/evidence${qs ? `?${qs}` : ''}`);
  },
  settings: () => request<SettingsResponse>('/api/settings'),
  saveSettings: (body: Partial<SettingsResponse['preferences']>) =>
    request<SettingsResponse>('/api/settings', { method: 'PUT', body: JSON.stringify(body) }),
  clearHistory: () => request<{ deleted_tasks: number }>('/api/history', { method: 'DELETE' }),
}
