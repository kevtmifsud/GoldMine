import { useEffect, useState } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import type { AnalystPack, WidgetConfig } from "../types/entities";
import { Layout } from "../components/Layout";
import { WidgetContainer } from "../components/WidgetContainer";
import { useAuth } from "../auth/useAuth";
import * as viewsApi from "../config/viewsApi";
import "../styles/packs.css";

export function PackPage() {
  const { packId } = useParams<{ packId: string }>();
  const navigate = useNavigate();
  const { user } = useAuth();

  const [pack, setPack] = useState<AnalystPack | null>(null);
  const [widgets, setWidgets] = useState<WidgetConfig[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!packId) return;
    setLoading(true);
    setError(null);

    Promise.all([
      viewsApi.getPack(packId),
      viewsApi.resolvePackWidgets(packId),
    ])
      .then(([packData, resolved]) => {
        setPack(packData);
        setWidgets(resolved);
      })
      .catch(() => {
        setError("Failed to load pack");
      })
      .finally(() => {
        setLoading(false);
      });
  }, [packId]);

  const handleDelete = async () => {
    if (!packId || !confirm("Delete this pack?")) return;
    await viewsApi.deletePack(packId);
    navigate("/packs");
  };

  const isOwner = pack?.owner === user?.username;

  return (
    <Layout>
      <div className="pack-page">
        <Link to="/packs" className="entity-page__back">
          &larr; Back to Packs
        </Link>
        {loading && (
          <div className="entity-page__loading">
            <div className="spinner" />
          </div>
        )}
        {error && <div className="entity-page__error">{error}</div>}
        {pack && (
          <>
            <div className="pack-page__header">
              <div>
                <h2 className="pack-page__name">{pack.name}</h2>
                {pack.description && (
                  <p className="pack-page__desc">{pack.description}</p>
                )}
                <div className="pack-page__meta">
                  <span>Owner: {pack.owner}</span>
                  {pack.is_shared && <span className="pack-page__shared-badge">Shared</span>}
                </div>
              </div>
              {isOwner && (
                <div className="pack-page__actions">
                  <button
                    className="view-toolbar__btn"
                    onClick={() => navigate(`/pack/${packId}/edit`)}
                  >
                    Edit
                  </button>
                  <button
                    className="view-toolbar__btn view-toolbar__btn--danger"
                    onClick={handleDelete}
                  >
                    Delete
                  </button>
                </div>
              )}
            </div>
            <div className="entity-page__widgets">
              {widgets.length === 0 && (
                <div className="packs-list__empty">
                  This pack has no widgets, or referenced entities are unavailable.
                </div>
              )}
              {widgets.map((widget, idx) => (
                <WidgetContainer key={`${widget.widget_id}-${idx}`} config={widget} />
              ))}
            </div>
          </>
        )}
      </div>
    </Layout>
  );
}
