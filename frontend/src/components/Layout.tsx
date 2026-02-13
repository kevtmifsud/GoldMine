import type { ReactNode } from "react";
import { Link, useLocation } from "react-router-dom";
import { useAuth } from "../auth/useAuth";
import { SearchBar } from "./SearchBar";
import "../styles/layout.css";

export function Layout({ children }: { children: ReactNode }) {
  const { user, logout } = useAuth();
  const { pathname } = useLocation();
  const isHome = pathname === "/";

  return (
    <div className="layout">
      <header className="header">
        <div className="header-left">
          <Link to="/" className="logo-link">
            <h1 className="logo">GoldMine</h1>
          </Link>
          {user && (
            <nav className="header-nav">
              <Link to="/packs" className="header-nav__link">My Packs</Link>
              <Link to="/alerts" className="header-nav__link">Alerts</Link>
            </nav>
          )}
        </div>
        {user && !isHome && (
          <div className="header-center">
            <SearchBar compact />
          </div>
        )}
        <div className="header-right">
          {user && (
            <>
              <span className="user-info">
                {user.display_name} ({user.role})
              </span>
              <button onClick={logout} className="logout-button">
                Logout
              </button>
            </>
          )}
        </div>
      </header>
      <main className="main-content">{children}</main>
    </div>
  );
}
