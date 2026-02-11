import { useEffect, useState, useCallback } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import api from "../config/api";
import type {
  EntityResolution,
  EntityDetail,
  PackWidgetRef,
  AnalystPack,
} from "../types/entities";
import { Layout } from "../components/Layout";
import * as viewsApi from "../config/viewsApi";
import "../styles/packs.css";

export function PackBuilderPage() {
  const { packId } = useParams<{ packId: string }>();
  const navigate = useNavigate();
  const isEdit = Boolean(packId);

  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [isShared, setIsShared] = useState(false);
  const [widgets, setWidgets] = useState<PackWidgetRef[]>([]);
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(isEdit);

  // Entity search state
  const [searchQuery, setSearchQuery] = useState("");
  const [searchLoading, setSearchLoading] = useState(false);
  const [searchResult, setSearchResult] = useState<EntityDetail | null>(null);
  const [searchError, setSearchError] = useState<string | null>(null);

  // Load existing pack for edit mode
  useEffect(() => {
    if (!packId) return;
    viewsApi
      .getPack(packId)
      .then((pack: AnalystPack) => {
        setName(pack.name);
        setDescription(pack.description);
        setIsShared(pack.is_shared);
        setWidgets(pack.widgets);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [packId]);

  const handleSearch = useCallback(async () => {
    const trimmed = searchQuery.trim();
    if (!trimmed) return;
    setSearchLoading(true);
    setSearchResult(null);
    setSearchError(null);
    try {
      const resolveResp = await api.get<EntityResolution>("/api/entities/resolve", {
        params: { q: trimmed },
      });
      const res = resolveResp.data;
      if (res.resolved && res.entity_type && res.entity_id) {
        const detailResp = await api.get<EntityDetail>(
          `/api/entities/${res.entity_type}/${res.entity_id}`
        );
        setSearchResult(detailResp.data);
      } else {
        setSearchError(res.message || "Entity not found");
      }
    } catch {
      setSearchError("Search failed");
    } finally {
      setSearchLoading(false);
    }
  }, [searchQuery]);

  const addWidget = (entityType: string, entityId: string, widgetId: string) => {
    setWidgets((prev) => [
      ...prev,
      {
        source_entity_type: entityType,
        source_entity_id: entityId,
        widget_id: widgetId,
        title_override: null,
        overrides: null,
      },
    ]);
  };

  const removeWidget = (idx: number) => {
    setWidgets((prev) => prev.filter((_, i) => i !== idx));
  };

  const moveWidget = (idx: number, direction: -1 | 1) => {
    const newIdx = idx + direction;
    if (newIdx < 0 || newIdx >= widgets.length) return;
    setWidgets((prev) => {
      const next = [...prev];
      [next[idx], next[newIdx]] = [next[newIdx], next[idx]];
      return next;
    });
  };

  const updateTitleOverride = (idx: number, title: string) => {
    setWidgets((prev) =>
      prev.map((w, i) =>
        i === idx ? { ...w, title_override: title || null } : w
      )
    );
  };

  const handleSave = async () => {
    if (!name.trim()) return;
    setSaving(true);
    try {
      if (isEdit && packId) {
        await viewsApi.updatePack(packId, {
          name: name.trim(),
          description: description.trim(),
          widgets,
          is_shared: isShared,
        });
        navigate(`/pack/${packId}`);
      } else {
        const created = await viewsApi.createPack({
          name: name.trim(),
          description: description.trim(),
          widgets,
          is_shared: isShared,
        });
        navigate(`/pack/${created.pack_id}`);
      }
    } catch {
      // Stay on page
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <Layout>
        <div className="entity-page__loading">
          <div className="spinner" />
        </div>
      </Layout>
    );
  }

  return (
    <Layout>
      <div className="pack-builder">
        <Link to="/packs" className="entity-page__back">
          &larr; Back to Packs
        </Link>
        <h2>{isEdit ? "Edit Pack" : "Create New Pack"}</h2>

        <div className="pack-builder__form">
          <div className="pack-builder__field">
            <label htmlFor="pack-name">Pack Name</label>
            <input
              id="pack-name"
              type="text"
              className="pack-builder__input"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="My Research Pack"
            />
          </div>
          <div className="pack-builder__field">
            <label htmlFor="pack-desc">Description</label>
            <textarea
              id="pack-desc"
              className="pack-builder__textarea"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Describe this pack..."
              rows={2}
            />
          </div>
          <label className="save-dialog__checkbox">
            <input
              type="checkbox"
              checked={isShared}
              onChange={(e) => setIsShared(e.target.checked)}
            />
            Share with team
          </label>
        </div>

        <div className="pack-builder__section">
          <h3>Add Widgets</h3>
          <div className="pack-builder__search-row">
            <input
              type="text"
              className="pack-builder__input"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleSearch()}
              placeholder="Search entity (e.g. AAPL, PER-001)..."
            />
            <button
              className="packs-list__create-btn"
              onClick={handleSearch}
              disabled={searchLoading || !searchQuery.trim()}
            >
              {searchLoading ? "Searching..." : "Search"}
            </button>
          </div>
          {searchError && (
            <p className="pack-builder__search-error">{searchError}</p>
          )}
          {searchResult && (
            <div className="pack-builder__search-results">
              <p className="pack-builder__entity-label">
                {searchResult.display_name} ({searchResult.entity_type})
              </p>
              <div className="pack-builder__widget-options">
                {searchResult.widgets.map((w) => (
                  <button
                    key={w.widget_id}
                    className="pack-builder__add-btn"
                    onClick={() =>
                      addWidget(
                        searchResult.entity_type,
                        searchResult.entity_id,
                        w.widget_id
                      )
                    }
                  >
                    + {w.title}
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>

        <div className="pack-builder__section">
          <h3>Selected Widgets ({widgets.length})</h3>
          {widgets.length === 0 && (
            <p className="pack-builder__empty">
              No widgets added yet. Search for entities above.
            </p>
          )}
          {widgets.map((w, idx) => (
            <div key={idx} className="pack-builder__widget-item">
              <div className="pack-builder__widget-info">
                <span className="pack-builder__widget-source">
                  {w.source_entity_type}/{w.source_entity_id}
                </span>
                <span className="pack-builder__widget-name">{w.widget_id}</span>
                <input
                  type="text"
                  className="pack-builder__title-input"
                  value={w.title_override ?? ""}
                  onChange={(e) => updateTitleOverride(idx, e.target.value)}
                  placeholder="Custom title (optional)"
                />
              </div>
              <div className="pack-builder__widget-actions">
                <button
                  className="pack-builder__move-btn"
                  onClick={() => moveWidget(idx, -1)}
                  disabled={idx === 0}
                >
                  Up
                </button>
                <button
                  className="pack-builder__move-btn"
                  onClick={() => moveWidget(idx, 1)}
                  disabled={idx === widgets.length - 1}
                >
                  Down
                </button>
                <button
                  className="pack-builder__remove-btn"
                  onClick={() => removeWidget(idx)}
                >
                  Remove
                </button>
              </div>
            </div>
          ))}
        </div>

        <div className="pack-builder__footer">
          <button
            className="packs-list__create-btn"
            onClick={handleSave}
            disabled={saving || !name.trim()}
          >
            {saving ? "Saving..." : isEdit ? "Update Pack" : "Create Pack"}
          </button>
        </div>
      </div>
    </Layout>
  );
}
