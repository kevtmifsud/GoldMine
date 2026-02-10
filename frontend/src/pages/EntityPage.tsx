import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import api from "../config/api";
import type { EntityDetail } from "../types/entities";
import { Layout } from "../components/Layout";
import { EntityHeader } from "../components/EntityHeader";
import { SmartlistWidget } from "../components/SmartlistWidget";
import "../styles/entity.css";

export function EntityPage() {
  const { entityType, entityId } = useParams<{
    entityType: string;
    entityId: string;
  }>();
  const [detail, setDetail] = useState<EntityDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!entityType || !entityId) return;

    setLoading(true);
    setError(null);
    setDetail(null);

    api
      .get<EntityDetail>(`/api/entities/${entityType}/${entityId}`)
      .then((resp) => {
        setDetail(resp.data);
      })
      .catch(() => {
        setError("Failed to load entity details");
      })
      .finally(() => {
        setLoading(false);
      });
  }, [entityType, entityId]);

  return (
    <Layout>
      <div className="entity-page">
        <Link to="/" className="entity-page__back">
          &larr; Back to Search
        </Link>
        {loading && (
          <div className="entity-page__loading">
            <div className="spinner" />
          </div>
        )}
        {error && <div className="entity-page__error">{error}</div>}
        {detail && (
          <>
            <EntityHeader
              displayName={detail.display_name}
              entityType={detail.entity_type}
              headerFields={detail.header_fields}
            />
            <div className="entity-page__widgets">
              {detail.widgets.map((widget) => (
                <SmartlistWidget key={widget.widget_id} config={widget} />
              ))}
            </div>
          </>
        )}
      </div>
    </Layout>
  );
}
