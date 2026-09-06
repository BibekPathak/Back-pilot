import type {
  Run,
  RunListResponse,
  Event,
  Intervention,
  DashboardStats,
  ActiveRunsResponse,
  RunCreatePayload,
  InterventionRequestPayload,
  InterventionResolvePayload,
  ResumePayload,
} from './types';

const BASE = '/api';

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`API error ${res.status}: ${body}`);
  }
  return res.json();
}

// Runs
export const api = {
  listRuns: (limit = 100) =>
    request<RunListResponse>(`/runs?limit=${limit}`),

  getRun: (id: string) =>
    request<Run>(`/runs/${id}`),

  getEvents: (runId: string) =>
    request<Event[]>(`/runs/${runId}/events`),

  createRun: (payload: RunCreatePayload) =>
    request<Run>('/runs', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  // Interventions
  getInterventions: (runId: string) =>
    request<Intervention[]>(`/runs/${runId}/interventions`),

  requestIntervention: (runId: string, payload: InterventionRequestPayload) =>
    request<Intervention>(`/runs/${runId}/intervention`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  resolveIntervention: (runId: string, ivId: number, payload: InterventionResolvePayload) =>
    request<Intervention>(`/runs/${runId}/intervention/${ivId}`, {
      method: 'PUT',
      body: JSON.stringify(payload),
    }),

  resumeRun: (runId: string, payload: ResumePayload) =>
    request<Intervention>(`/runs/${runId}/resume`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  // Dashboard
  getStats: () =>
    request<DashboardStats>('/dashboard/stats'),

  getActiveRuns: () =>
    request<ActiveRunsResponse>('/dashboard/runs/active'),

  // Health
  health: () =>
    request<{ status: string }>('/health'),
};
