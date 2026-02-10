import { Layout } from "../components/Layout";
import { useAuth } from "../auth/useAuth";

export function HomePage() {
  const { user } = useAuth();

  return (
    <Layout>
      <div className="home-page">
        <h2>Welcome, {user?.display_name}</h2>
        <p className="subtitle">
          GoldMine Investment Research CRM — Phase 0 Shell
        </p>
        <div className="status-cards">
          <div className="status-card">
            <h3>Your Role</h3>
            <p>{user?.role}</p>
          </div>
          <div className="status-card">
            <h3>System Status</h3>
            <p>All systems operational</p>
          </div>
          <div className="status-card">
            <h3>Phase</h3>
            <p>0 — Foundations</p>
          </div>
        </div>
      </div>
    </Layout>
  );
}
