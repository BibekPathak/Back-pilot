import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../api';
import type { Run } from '../types';
import { STATE_COLORS } from '../types';

export default function RunsList() {
  const [runs, setRuns] = useState<Run[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.listRuns(50).then(data => {
      setRuns(data.runs);
      setTotal(data.total);
      setLoading(false);
    });
  }, []);

  if (loading) return <div className="p-4">Loading...</div>;

  return (
    <div>
      <div className="flex justify-between items-center mb-4">
        <h2 className="text-2xl font-bold">Runs ({total})</h2>
        <Link
          to="/runs/new"
          className="bg-blue-600 text-white px-4 py-2 rounded hover:bg-blue-700"
        >
          New Run
        </Link>
      </div>

      <table className="w-full bg-white rounded-lg shadow">
        <thead>
          <tr className="border-b text-left text-sm text-gray-500">
            <th className="p-3">ID</th>
            <th className="p-3">State</th>
            <th className="p-3">Scenario</th>
            <th className="p-3">Task</th>
            <th className="p-3">Started</th>
            <th className="p-3">Result</th>
          </tr>
        </thead>
        <tbody>
          {runs.map(r => (
            <tr key={r.id} className="border-b hover:bg-gray-50">
              <td className="p-3">
                <Link to={`/runs/${r.id}`} className="text-blue-600 hover:underline font-mono text-sm">
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
              <td className="p-3">{r.scenario}</td>
              <td className="p-3 max-w-xs truncate">{r.task}</td>
              <td className="p-3 text-sm text-gray-500">
                {new Date(r.started_at).toLocaleString()}
              </td>
              <td className="p-3 text-sm">{r.result || '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
