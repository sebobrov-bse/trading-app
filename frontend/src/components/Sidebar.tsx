import { NavLink } from 'react-router-dom';

const links = [
  { to: '/', label: 'Dashboard', end: true },
  { to: '/backtest', label: 'Backtest' },
  { to: '/history', label: 'History' },
  { to: '/data', label: 'Data' },
];

export function Sidebar() {
  return (
    <aside className="sidebar">
      <div className="sidebar-brand">Trading App</div>
      <nav className="sidebar-nav">
        {links.map((link) => (
          <NavLink
            key={link.to}
            to={link.to}
            end={link.end}
            className={({ isActive }) =>
              isActive ? 'nav-link nav-link-active' : 'nav-link'
            }
          >
            {link.label}
          </NavLink>
        ))}
      </nav>
    </aside>
  );
}