import { useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { api } from '../api';
import type { Run, Event, Intervention } from '../types';
import { STATE_COLORS } from '../types';

function StateBadge({ state }: { state: string }) {
  return (
    <span
      className="px-3 py-1 rounded text-white text-sm font-medium"
      style={{ backgroundColor: STATE_COLORS[state] || '#6b7280' }}
    >
      {state}
    </span>
  );
}

function EventRow({ ev }: { ev: Event }) {
  const kindColors: Record<string, string> = {
    action: '#3b82f6',
    observation: '#6b7280',
    recovery: '#eab308',
    state_change: '#8b5cf6',
    error: '#ef4444',
    planner_decision: '#06b6d4',
    screenshot: '#14b8a6',
  };
  return (
    <tr className="border-b hover:bg-gray-50">
      <td className="p-2 text-sm text-gray-500">{ev.seq}</td>
      <td className="p-2">
        <span
          className="px-2 py-0.5 rounded text-white text-xs"
          style={{ backgroundColor: kindColors[ev.kind] || '#6b7280' }}
        >
          {ev.kind}
        </span>
      </td>
      <td className="p-2 text-sm font-mono">{ev.action || '—'}</td>
      <td className="p-2 text-sm">{ev.target || '—'}</td>
      <td className="p-2 text-sm">{ev.result || '—'}</td>
      <td className="p-2 text-sm max-w-xs truncate">{ev.detail || '—'}</td>
      <td className="p-2 text-sm text-gray-500">{ev.duration_ms ?? '—'}ms</td>
    </tr>
  );
}

function InterventionPanel({ runId, interventions, onRefresh }: {
  runId: string;
  interventions: Intervention[];
  onRefresh: () => void;
}) {
  const [reason, setReason] = useState('');
  const [note, setNote] = useState('');
  const [loading, setLoading] = useState(false);

  const handleRequest = async () => {
    if (!reason) return;
    setLoading(true);
    await api.requestIntervention(runId, { reason });
    setReason('');
    onRefresh();
    setLoading(false);
  };

  const handleResolve = async (ivId: number) => {
    setLoading(true);
    await api.resolveIntervention(runId, ivId, { resolution_note: note || 'resolved' });
    setNote('');
    onRefresh();
    setLoading(false);
  };

  const handleResume = async (action: 'continue' | 'abort') => {
    setLoading(true);
    await api.resumeRun(runId, { action, note: action === 'abort' ? 'aborted by human' : 'resuming' });
    onRefresh();
    setLoading(false);
  };

  const pending = interventions.filter(i => i.status === 'pending');

  return (
    <div className="bg-white rounded-lg shadow p-4 mt-4">
      <h3 className="text-lg font-bold mb-3">Human Intervention</h3>

      {pending.length > 0 && (
        <div className="flex gap-2 mb-3">
          <button
            onClick={() => handleResume('continue')}
            disabled={loading}
            className="bg-green-600 text-white px-3 py-1 rounded hover:bg-green-700 disabled:opacity-50"
          >
            Resume
          </button>
          <button
            onClick={() => handleResume('abort')}
            disabled={loading}
            className="bg-red-600 text-white px-3 py-1 rounded hover:bg-red-700 disabled:opacity-50"
          >
            Abort
          </button>
        </div>
      )}

      <div className="flex gap-2 mb-4">
        <input
          type="text"
          value={reason}
          onChange={e => setReason(e.target.value)}
          placeholder="Intervention reason..."
          className="border rounded px-3 py-1 flex-1"
        />
        <button
          onClick={handleRequest}
          disabled={loading || !reason}
          className="bg-yellow-500 text-white px-3 py-1 rounded hover:bg-yellow-600 disabled:opacity-50"
        >
          Request
        </button>
      </div>

      {interventions.length > 0 && (
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b text-left text-gray-500">
              <th className="p-2">ID</th>
              <th className="p-2">Reason</th>
              <th className="p-2">Status</th>
              <th className="p-2">Requested</th>
              <th className="p-2">Resolved</th>
              <th className="p-2">Action</th>
            </tr>
          </thead>
          <tbody>
            {interventions.map(iv => (
              <tr key={iv.id} className="border-b">
                <td className="p-2">{iv.id}</td>
                <td className="p-2">{iv.reason}</td>
                <td className="p-2">
                  <span className={`px-2 py-0.5 rounded text-xs ${
                    iv.status === 'resolved' ? 'bg-green-100 text-green-800' :
                    iv.status === 'pending' ? 'bg-yellow-100 text-yellow-800' :
                    'bg-gray-100 text-gray-800'
                  }`}>
                    {iv.status}
                  </span>
                </td>
                <td className="p-2">{new Date(iv.requested_at).toLocaleString()}</td>
                <td className="p-2">{iv.resolved_at ? new Date(iv.resolved_at).toLocaleString() : '—'}</td>
                <td className="p-2">
                  {iv.status === 'pending' && (
                    <div className="flex gap-1">
                      <input
                        type="text"
                        value={note}
                        onChange={e => setNote(e.target.value)}
                        placeholder="Note..."
                        className="border rounded px-2 py-0.5 text-xs w-32"
                      />
                      <button
                        onClick={() => handleResolve(iv.id)}
                        disabled={loading}
                        className="bg-blue-500 text-white px-2 py-0.5 rounded text-xs hover:bg-blue-600"
                      >
                        Resolve
                      </button>
                    </div>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

export default function RunDetail() {
  const { id } = useParams<{ id: string }>();
  const [run, setRun] = useState<Run | null>(null);
  const [events, setEvents] = useState<Event[]>([]);
  const [interventions, setInterventions] = useState<Intervention[]>([]);
  const [error, setError] = useState('');

  const load = () => {
    if (!id) return;
    api.getRun(id).then(setRun).catch(e => setError(String(e)));
    api.getEvents(id).then(setEvents).catch(() => {});
    api.getInterventions(id).then(setInterventions).catch(() => {});
  };

  useEffect(load, [id]);

  if (error) return <div className="text-red-600 p-4">Error: {error}</div>;
  if (!run) return <div className="p-4">Loading...</div>;

  return (
    <div>
      <div className="flex items-center gap-4 mb-4">
        <Link to="/runs" className="text-blue-600 hover:underline">&larr; Back</Link>
        <h2 className="text-2xl font-bold">Run {run.id}</h2>
        <StateBadge state={run.state} />
      </div>

      <div className="bg-white rounded-lg shadow p-4 mb-4 grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
        <div>
          <span className="text-gray-500">Scenario:</span> {run.scenario}
        </div>
        <div>
          <span className="text-gray-500">Started:</span> {new Date(run.started_at).toLocaleString()}
        </div>
        <div>
          <span className="text-gray-500">Finished:</span>{' '}
          {run.finished_at ? new Date(run.finished_at).toLocaleString() : '—'}
        </div>
        <div>
          <span className="text-gray-500">Result:</span> {run.result || '—'}
        </div>
      </div>

      <div className="bg-white rounded-lg shadow p-4 mb-4">
        <h3 className="text-lg font-bold mb-2">Task</h3>
        <p className="text-gray-700">{run.task}</p>
      </div>

      <InterventionPanel runId={run.id} interventions={interventions} onRefresh={load} />

      <h3 className="text-xl font-bold mt-6 mb-3">Event Timeline ({events.length})</h3>
      <table className="w-full bg-white rounded-lg shadow">
        <thead>
          <tr className="border-b text-left text-sm text-gray-500">
            <th className="p-2">#</th>
            <th className="p-2">Kind</th>
            <th className="p-2">Action</th>
            <th className="p-2">Target</th>
            <th className="p-2">Result</th>
            <th className="p-2">Detail</th>
            <th className="p-2">Duration</th>
          </tr>
        </thead>
        <tbody>
          {events.map(ev => <EventRow key={ev.id} ev={ev} />)}
        </tbody>
      </table>
    </div>
  );
}
