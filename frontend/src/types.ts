export interface Run {
  id: string;
  scenario: string;
  task: string;
  state: string;
  started_at: string;
  finished_at: string | null;
  result: string | null;
}

export interface RunListResponse {
  runs: Run[];
  total: number;
}

export interface Event {
  id: number;
  run_id: string;
  seq: number;
  timestamp: string;
  state: string | null;
  kind: string;
  action: string | null;
  target: string | null;
  result: string | null;
  failure_reason: string | null;
  detail: string | null;
  duration_ms: number | null;
  screenshot_path: string | null;
}

export interface Intervention {
  id: number;
  run_id: string;
  reason: string;
  status: string;
  assigned_to: string | null;
  resolution_note: string | null;
  requested_at: string;
  notified_at: string | null;
  resolved_at: string | null;
}

export interface DashboardStats {
  total_runs: number;
  success: number;
  failed: number;
  human_intervention: number;
  success_rate: number;
  pending_interventions: number;
}

export interface ActiveRun {
  id: string;
  state: string;
  task: string;
}

export interface ActiveRunsResponse {
  runs: ActiveRun[];
}

export interface RunCreatePayload {
  scenario?: string;
  task: string;
}

export interface InterventionRequestPayload {
  reason: string;
  assigned_to?: string;
}

export interface InterventionResolvePayload {
  resolution_note: string;
  status?: string;
}

export interface ResumePayload {
  action: 'continue' | 'abort';
  note?: string;
}

export const RUN_STATES = [
  'CREATED', 'PLANNING', 'NAVIGATING', 'FILLING_FORM', 'UPLOADING',
  'VALIDATING', 'SUBMITTING', 'SUCCESS', 'ACTION_FAILED', 'RECOVERING',
  'HUMAN_INTERVENTION', 'FAILED',
] as const;

export type RunState = typeof RUN_STATES[number];

export const STATE_COLORS: Record<string, string> = {
  CREATED: '#6b7280',
  PLANNING: '#8b5cf6',
  NAVIGATING: '#3b82f6',
  FILLING_FORM: '#06b6d4',
  UPLOADING: '#14b8a6',
  VALIDATING: '#f59e0b',
  SUBMITTING: '#f97316',
  SUCCESS: '#22c55e',
  ACTION_FAILED: '#ef4444',
  RECOVERING: '#eab308',
  HUMAN_INTERVENTION: '#f43f5e',
  FAILED: '#dc2626',
};
