import { useEffect, useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import type { Studio } from "../types/studio";
import { Layout } from "../components/Layout";
import { useAuth } from "../auth/useAuth";
import * as studiosApi from "../config/studiosApi";
import "../styles/studio.css";

export function StudiosListPage() {
  const [studios, setStudios] = useState<Studio[]>([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const { user } = useAuth();
  const navigate = useNavigate();

  useEffect(() => {
    setLoading(true);
    studiosApi
      .listStudios()
      .then(setStudios)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const handleCreate = async () => {
    setCreating(true);
    try {
      const studio = await studiosApi.createStudio({
        name: "Untitled Studio",
        description: "",
        is_shared: false,
      });
      navigate(`/studio/${studio.studio_id}`);
    } catch {
      setCreating(false);
    }
  };

  const handleDelete = async (e: React.MouseEvent, studio: Studio) => {
    e.preventDefault();
    e.stopPropagation();
    if (!confirm(`Delete studio "${studio.name}"?`)) return;
    setDeletingId(studio.studio_id);
    try {
      await studiosApi.deleteStudio(studio.studio_id);
      setStudios((prev) => prev.filter((s) => s.studio_id !== studio.studio_id));
    } catch {
      // stay
    } finally {
      setDeletingId(null);
    }
  };

  return (
    <Layout>
      <div className="studios-list">
        <div className="studios-list__header">
          <h2>Data Studio</h2>
          <button
            className="studios-list__create-btn"
            onClick={handleCreate}
            disabled={creating}
          >
            {creating ? "Creating..." : "New Studio"}
          </button>
        </div>
        {loading && (
          <div className="studios-list__loading">
            <div className="spinner" />
          </div>
        )}
        {!loading && studios.length === 0 && (
          <div className="studios-list__empty">
            No studios yet. Create your first studio to start building charts with AI.
          </div>
        )}
        {!loading && studios.length > 0 && (
          <div className="studios-list__grid">
            {studios.map((studio) => (
              <Link
                key={studio.studio_id}
                to={`/studio/${studio.studio_id}`}
                className="studios-list__card"
              >
                <span className="studios-list__card-name">{studio.name}</span>
                {studio.description && (
                  <span className="studios-list__card-desc">
                    {studio.description}
                  </span>
                )}
                <div className="studios-list__card-meta">
                  <span>{studio.owner_display_name || studio.owner}</span>
                  {studio.is_shared && (
                    <span className="studios-list__card-badge">Shared</span>
                  )}
                  <span>{studio.widgets.length} chart{studio.widgets.length !== 1 ? "s" : ""}</span>
                </div>
                {studio.owner === user?.username && (
                  <div className="studios-list__card-actions">
                    <button
                      className="studios-list__delete-btn"
                      onClick={(e) => handleDelete(e, studio)}
                      disabled={deletingId === studio.studio_id}
                    >
                      {deletingId === studio.studio_id ? "Deleting..." : "Delete"}
                    </button>
                  </div>
                )}
              </Link>
            ))}
          </div>
        )}
      </div>
    </Layout>
  );
}
