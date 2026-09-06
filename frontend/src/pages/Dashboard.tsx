import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../api';
import type { DashboardStats, ActiveRun } from '../types';
import { STATE_COLORS } from '../types';

export default function Dashboard() {
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [active, setActive] = useState<ActiveRun[]>([]);
  const [error, setError] = useState('');

  useEffect(() => {
    api.getStats().then(setStats).catch(e => setError(String(e)));
    api.getActiveRuns().then(r => setActive(r.runs)).catch(() => {});
  }, []);

  if (error) return <div className="text-red-600 p-4">Error: {error}</div>;
  if (!stats) return <div className="p-4">Loading...</div>;

  const cards = [
    { label: 'Total Runs', value: stats.total_runs, color: '#3b82f6' },
    { label: 'Success', value: stats.success, color: '#22c55e' },
    { label: 'Failed', value: stats.failed, color: '#dc2626' },
    { label: 'Human Intervention', value: stats.human_intervention, color: '#f43f5e' },
    { label: 'Pending Interventions', value: stats.pending_interventions, color: '#f59e0b' },
  ];

  return (
    <div>
      <h2 className="text-2xl font-bold mb-4">Dashboard</h2>

      <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mb-8">
        {cards.map(c => (
          <div key={c.label} className="bg-white rounded-lg shadow p-4">
            <div className="text-sm text-gray-500">{c.label}</div>
            <div className="text-3xl font-bold" style={{ color: c.color }}>
              {c.value}
            </div>
          </div>
        ))}
      </div>

      <div className="bg-white rounded-lg shadow p-4 mb-4">
        <div className="text-sm text-gray-500">Success Rate</div>
        <div className="text-2xl font-bold text-green-600">
          {stats.success_rate}%
        </div>
      </div>

      <h3 className="text-xl font-bold mb-3">Active Runs</h3>
      {active.length === 0 ? (
        <p className="text-gray-500">No active runs.</p>
      ) : (
        <table className="w-full bg-white rounded-lg shadow">
          <thead>
            <tr className="border-b text-left text-sm text-gray-500">
              <th className="p-3">Run ID</th>
              <th className="p-3">State</th>
              <th className="p-3">Task</th>
            </tr>
          </thead>
          <tbody>
            {active.map(r => (
              <tr key={r.id} className="border-b hover:bg-gray-50">
                <td className="p-3">
                  <Link to={`/runs/${r.id}`} className="text-blue-600 hover:underline">
                    {r.id}
                  </Link>
                </td>
                <td className="p-3">
                  <span
                    className="px-2 py-1 rounded text-white text-sm"
                    style={{ backgroundColor: STATE_COLORS[r.state] || '#6b7280' }}
                  >
                    {r.state}
                  </span>
                </td>
                <td className="p-3">{r.task}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
