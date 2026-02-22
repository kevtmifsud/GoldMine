import { NavLink, Link } from "react-router-dom";

interface StockSidebarProps {
  displayName: string;
  entityId: string;
}

const NAV_ITEMS = [
  { to: "details", label: "Details" },
  { to: "portfolio", label: "Portfolio & Positions" },
  { to: "contacts", label: "Contacts" },
  { to: "research", label: "Research" },
  { to: "data", label: "Data" },
  { to: "alerts", label: "Alerts" },
];

export function StockSidebar({ displayName, entityId }: StockSidebarProps) {
  return (
    <aside className="stock-sidebar">
      <div className="stock-sidebar__header">
        <div className="stock-sidebar__name">{displayName}</div>
        <span className="stock-sidebar__badge">Stock</span>
      </div>
      <nav className="stock-sidebar__nav">
        {NAV_ITEMS.map((item) => (
          <NavLink
            key={item.to}
            to={`/entity/stock/${entityId}/${item.to}`}
            className={({ isActive }) =>
              `stock-sidebar__link${isActive ? " active" : ""}`
            }
          >
            {item.label}
          </NavLink>
        ))}
      </nav>
      <div className="stock-sidebar__back">
        <Link to="/">&larr; Back to Search</Link>
      </div>
    </aside>
  );
}
