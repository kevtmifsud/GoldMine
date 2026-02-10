import type { ReactNode } from "react";
import { useAuth } from "../auth/useAuth";
import "../styles/layout.css";

export function Layout({ children }: { children: ReactNode }) {
  const { user, logout } = useAuth();

  return (
    <div className="layout">
      <header className="header">
        <div className="header-left">
          <h1 className="logo">GoldMine</h1>
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
