import type { ReactNode } from "react";
import { Link, useLocation } from "react-router-dom";
import { useAuth } from "../auth/useAuth";
import { SearchBar } from "./SearchBar";
import { GlobalChatPanel } from "./GlobalChatPanel";
import { useGlobalChat } from "../context/GlobalChatContext";
import "../styles/layout.css";

export function Layout({ children, contentClassName }: { children: ReactNode; contentClassName?: string }) {
  const { user, logout } = useAuth();
  const { pathname } = useLocation();
  const isHome = pathname === "/";
  const { isOpen, open } = useGlobalChat();
  const isChatPage = pathname === "/chat";

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
              <Link to="/chat" className="header-nav__link">Chat</Link>
              <Link to="/portfolios" className="header-nav__link">Portfolios</Link>
              <Link to="/earnings" className="header-nav__link">Earnings</Link>
              <Link to="/alerts" className="header-nav__link">Alerts</Link>
              <Link to="/reports" className="header-nav__link">Reports</Link>
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
      <main className={`main-content${contentClassName ? ` ${contentClassName}` : ""}`}>{children}</main>

      {/* Global chat trigger tab — hidden on /chat page and when panel is open */}
      {user && !isChatPage && !isOpen && (
        <button className="chat-trigger" onClick={open} title="Chat (Cmd+/)">
          Chat
        </button>
      )}

      {/* Global chat panel */}
      {user && !isChatPage && <GlobalChatPanel />}

      {/* Persistent hint */}
      {user && !isChatPage && !isOpen && (
        <div className="chat-hint-banner">
          Chat available everywhere — &#8984;/ to open
        </div>
      )}
    </div>
  );
}
