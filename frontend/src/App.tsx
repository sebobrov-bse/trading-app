import { BrowserRouter, Route, Routes } from 'react-router-dom';
import { Layout } from './components/Layout';
import { Dashboard } from './pages/Dashboard';
import { Backtest } from './pages/Backtest';
import { History } from './pages/History';
import { Data } from './pages/Data';

export function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route path="/" element={<Dashboard />} />
          <Route path="/backtest" element={<Backtest />} />
          <Route path="/history" element={<History />} />
          <Route path="/data" element={<Data />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}