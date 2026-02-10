import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "../auth/useAuth";
import "../styles/layout.css";

export function Layout({ children }: { children: ReactNode }) {
  const { user, logout } = useAuth();

  return (
    <div className="layout">
      <header className="header">
        <div className="header-left">
          <Link to="/" className="logo-link">
            <h1 className="logo">GoldMine</h1>
          </Link>
        </div>
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
