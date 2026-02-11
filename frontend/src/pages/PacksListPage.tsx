import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import type { AnalystPack } from "../types/entities";
import { Layout } from "../components/Layout";
import { useAuth } from "../auth/useAuth";
import * as viewsApi from "../config/viewsApi";
import "../styles/packs.css";

export function PacksListPage() {
  const [packs, setPacks] = useState<AnalystPack[]>([]);
  const [loading, setLoading] = useState(true);
  const { user } = useAuth();
  const navigate = useNavigate();

  useEffect(() => {
    viewsApi
      .listPacks()
      .then(setPacks)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  return (
    <Layout>
      <div className="packs-list">
        <div className="packs-list__header">
          <h2>My Packs</h2>
          <button
            className="packs-list__create-btn"
            onClick={() => navigate("/pack/new")}
          >
            Create New Pack
          </button>
        </div>
        {loading && (
          <div className="packs-list__loading">
            <div className="spinner" />
          </div>
        )}
        {!loading && packs.length === 0 && (
          <div className="packs-list__empty">
            No packs yet. Create your first analyst pack to get started.
          </div>
        )}
        {!loading && packs.length > 0 && (
          <div className="packs-list__grid">
            {packs.map((pack) => (
              <Link
                key={pack.pack_id}
                to={`/pack/${pack.pack_id}`}
                className="pack-card"
              >
                <h3 className="pack-card__name">{pack.name}</h3>
                {pack.description && (
                  <p className="pack-card__desc">{pack.description}</p>
                )}
                <div className="pack-card__meta">
                  <span>{pack.widgets.length} widget{pack.widgets.length !== 1 ? "s" : ""}</span>
                  <span>
                    {pack.owner === user?.username ? "You" : pack.owner}
                    {pack.is_shared && " (shared)"}
                  </span>
                </div>
              </Link>
            ))}
          </div>
        )}
      </div>
    </Layout>
  );
}
