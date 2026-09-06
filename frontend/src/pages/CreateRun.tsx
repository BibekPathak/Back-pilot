import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '../api';

const SCENARIOS = [
  'baseline',
  'happy_path',
  'selector_change',
  'slow_network',
  'missing_element',
  'unexpected_modal',
  'session_expired',
  'upload_failure',
  'captcha',
];

export default function CreateRun() {
  const navigate = useNavigate();
  const [scenario, setScenario] = useState('baseline');
  const [task, setTask] = useState(
    'Log in to the ACME ERP portal, fill in invoice INV-29381 for vendor ACME Corp with amount 1250.00, upload the invoice PDF, and submit.'
  );
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError('');
    try {
      const run = await api.createRun({ scenario, task });
      navigate(`/runs/${run.id}`);
    } catch (err) {
      setError(String(err));
      setLoading(false);
    }
  };

  return (
    <div>
      <h2 className="text-2xl font-bold mb-4">Create New Run</h2>

      <form onSubmit={handleSubmit} className="bg-white rounded-lg shadow p-6 max-w-2xl">
        <div className="mb-4">
          <label className="block text-sm font-medium text-gray-700 mb-1">Scenario</label>
          <select
            value={scenario}
            onChange={e => setScenario(e.target.value)}
            className="w-full border rounded px-3 py-2"
          >
            {SCENARIOS.map(s => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
        </div>

        <div className="mb-4">
          <label className="block text-sm font-medium text-gray-700 mb-1">Task</label>
          <textarea
            value={task}
            onChange={e => setTask(e.target.value)}
            rows={4}
            className="w-full border rounded px-3 py-2"
          />
        </div>

        {error && (
          <div className="text-red-600 text-sm mb-4">{error}</div>
        )}

        <button
          type="submit"
          disabled={loading || !task}
          className="bg-blue-600 text-white px-6 py-2 rounded hover:bg-blue-700 disabled:opacity-50"
        >
          {loading ? 'Creating...' : 'Create Run'}
        </button>
      </form>
    </div>
  );
}
