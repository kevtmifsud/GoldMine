import { useEffect, useState } from "react";
import { PackGrid } from "./PackGrid";
import { usePackEditor } from "../hooks/usePackEditor";
import * as viewsApi from "../config/viewsApi";
import "../styles/packs.css";

interface EntityPackSectionProps {
  entityType: string;
  entityId: string;
}

export function EntityPackSection({ entityType, entityId }: EntityPackSectionProps) {
  const [packId, setPackId] = useState<string | null>(null);
  const [fetchError, setFetchError] = useState<string | null>(null);

  useEffect(() => {
    setPackId(null);
    setFetchError(null);
    viewsApi
      .getEntityPack(entityType, entityId)
      .then((pack) => setPackId(pack.pack_id))
      .catch(() => setFetchError("Failed to load analyst pack"));
  }, [entityType, entityId]);

  const editor = usePackEditor(packId, true);

  if (fetchError) {
    return (
      <div className="entity-pack-section">
        <div className="entity-pack-section__header">
          <h3>Analyst Pack</h3>
        </div>
        <div className="entity-page__error">{fetchError}</div>
      </div>
    );
  }

  if (!packId || editor.loading) {
    return (
      <div className="entity-pack-section">
        <div className="entity-pack-section__header">
          <h3>Analyst Pack</h3>
        </div>
        <div className="entity-page__loading">
          <div className="spinner" />
        </div>
      </div>
    );
  }

  return (
    <div className="entity-pack-section">
      <div className="entity-pack-section__header">
        <h3>Analyst Pack</h3>
        {editor.dirty && (
          <button
            className="entity-page__action-btn entity-page__action-btn--primary"
            onClick={editor.handleSave}
            disabled={editor.saving}
          >
            {editor.saving ? "Saving..." : "Save"}
          </button>
        )}
      </div>
      <PackGrid editor={editor} />
    </div>
  );
}
