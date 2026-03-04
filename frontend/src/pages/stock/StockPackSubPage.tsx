import { useEffect, useState } from "react";
import { useStockEntity } from "./StockEntityPage";
import { PackGrid } from "../../components/PackGrid";
import { ResearchSearchBar } from "../../components/ResearchSearchBar";
import { usePackEditor } from "../../hooks/usePackEditor";
import * as viewsApi from "../../config/viewsApi";
import "../../styles/packs.css";

export function StockPackSubPage() {
  const { detail } = useStockEntity();
  const [packId, setPackId] = useState<string | null>(null);
  const [fetchError, setFetchError] = useState<string | null>(null);

  useEffect(() => {
    viewsApi
      .getEntityPack(detail.entity_type, detail.entity_id)
      .then((pack) => setPackId(pack.pack_id))
      .catch(() => setFetchError("Failed to load analyst pack"));
  }, [detail.entity_type, detail.entity_id]);

  const editor = usePackEditor(packId, true);

  if (fetchError) {
    return (
      <>
        <ResearchSearchBar entityType={detail.entity_type} entityId={detail.entity_id} />
        <div className="entity-page__error">{fetchError}</div>
      </>
    );
  }

  if (!packId || editor.loading) {
    return (
      <>
        <ResearchSearchBar entityType={detail.entity_type} entityId={detail.entity_id} />
        <div className="entity-page__loading">
          <div className="spinner" />
        </div>
      </>
    );
  }

  return (
    <>
      <ResearchSearchBar entityType={detail.entity_type} entityId={detail.entity_id} />
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
    </>
  );
}
