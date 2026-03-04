import { NavLink, Link, useLocation } from "react-router-dom";

interface StockSidebarProps {
  displayName: string;
  entityId: string;
}

interface NavChild {
  to: string;
  label: string;
}

interface NavItem {
  to: string;
  label: string;
  children?: NavChild[];
}

const NAV_ITEMS: NavItem[] = [
  { to: "portfolio", label: "Portfolio & Positions" },
  { to: "contacts", label: "Contacts" },
  {
    to: "research",
    label: "Research",
    children: [
      { to: "research", label: "All Documents" },
      { to: "research/transcripts", label: "Transcripts" },
      { to: "research/filings", label: "SEC Filings" },
      { to: "research/sellside", label: "Sell-side" },
      { to: "research/data-files", label: "Data Files" },
      { to: "research/notes", label: "Notes" },
      { to: "research/other", label: "Other" },
    ],
  },
  {
    to: "fundamentals",
    label: "Fundamentals",
    children: [
      { to: "fundamentals", label: "Summary" },
      { to: "fundamentals/income-statement", label: "Income Statement" },
      { to: "fundamentals/balance-sheet", label: "Balance Sheet" },
      { to: "fundamentals/cash-flow", label: "Cash Flow" },
    ],
  },
  { to: "data", label: "Data" },
  { to: "alerts", label: "Alerts" },
  { to: "pack", label: "Analyst Pack" },
];

export function StockSidebar({ displayName, entityId }: StockSidebarProps) {
  const location = useLocation();
  const basePath = `/entity/stock/${entityId}`;

  return (
    <aside className="stock-sidebar">
      <div className="stock-sidebar__header">
        <div className="stock-sidebar__name">{displayName}</div>
        <span className="stock-sidebar__badge">Stock</span>
      </div>
      <nav className="stock-sidebar__nav">
        {NAV_ITEMS.map((item) => (
          <div key={item.to}>
            <NavLink
              to={`${basePath}/${item.to}`}
              end={!item.children}
              className={({ isActive }) =>
                `stock-sidebar__link${isActive ? " active" : ""}`
              }
            >
              {item.label}
            </NavLink>
            {item.children && location.pathname.startsWith(`${basePath}/${item.to}`) && (
              <div className="stock-sidebar__sub-nav">
                {item.children.map((child) => (
                  <NavLink
                    key={child.to}
                    to={`${basePath}/${child.to}`}
                    end
                    className={({ isActive }) =>
                      `stock-sidebar__sub-link${isActive ? " active" : ""}`
                    }
                  >
                    {child.label}
                  </NavLink>
                ))}
              </div>
            )}
          </div>
        ))}
      </nav>
      <div className="stock-sidebar__back">
        <Link to="/">&larr; Back to Search</Link>
      </div>
    </aside>
  );
}
