import { BrowserRouter, Routes, Route, NavLink } from 'react-router-dom';
import Dashboard from './pages/Dashboard';
import RunsList from './pages/RunsList';
import RunDetail from './pages/RunDetail';
import CreateRun from './pages/CreateRun';

function NavBar() {
  const linkClass = ({ isActive }: { isActive: boolean }) =>
    `px-4 py-2 rounded ${isActive ? 'bg-blue-600 text-white' : 'text-gray-700 hover:bg-gray-100'}`;

  return (
    <nav className="bg-white shadow mb-6">
      <div className="max-w-7xl mx-auto px-4 py-3 flex items-center gap-6">
        <h1 className="text-xl font-bold text-blue-600">BackPilot</h1>
        <div className="flex gap-2">
          <NavLink to="/" className={linkClass} end>Dashboard</NavLink>
          <NavLink to="/runs" className={linkClass}>Runs</NavLink>
          <NavLink to="/runs/new" className={linkClass}>New Run</NavLink>
        </div>
      </div>
    </nav>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <NavBar />
      <main className="max-w-7xl mx-auto px-4">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/runs" element={<RunsList />} />
          <Route path="/runs/new" element={<CreateRun />} />
          <Route path="/runs/:id" element={<RunDetail />} />
        </Routes>
      </main>
    </BrowserRouter>
  );
}
