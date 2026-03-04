import { useState } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import { Layout } from "../components/Layout";
import { PackGrid } from "../components/PackGrid";
import { ScheduleEmailDialog } from "../components/ScheduleEmailDialog";
import { useAuth } from "../auth/useAuth";
import { usePackEditor } from "../hooks/usePackEditor";
import * as viewsApi from "../config/viewsApi";
import "../styles/entity.css";
import "../styles/packs.css";

export function PackPage() {
  const { packId } = useParams<{ packId: string }>();
  const navigate = useNavigate();
  const { user } = useAuth();

  const [showAlertDialog, setShowAlertDialog] = useState(false);

  // Editing header fields
  const [editingName, setEditingName] = useState(false);
  const [editingDesc, setEditingDesc] = useState(false);

  // Header state (name/desc/shared managed locally since they're PackPage-specific)
  const [packName, setPackName] = useState("");
  const [packDesc, setPackDesc] = useState("");
  const [packShared, setPackShared] = useState(false);
  const [headerInitialized, setHeaderInitialized] = useState(false);

  const isOwner = true; // Will be refined after pack loads
  const editor = usePackEditor(packId ?? null, isOwner);

  // Sync header state from pack when it loads
  if (editor.pack && !headerInitialized) {
    setPackName(editor.pack.name);
    setPackDesc(editor.pack.description);
    setPackShared(editor.pack.is_shared);
    setHeaderInitialized(true);
  }

  const actualIsOwner = editor.pack?.owner === user?.username;

  const headerDirty =
    editor.pack != null &&
    (packName !== editor.pack.name ||
      packDesc !== editor.pack.description ||
      packShared !== editor.pack.is_shared);

  const handleSave = async () => {
    if (!editor.dirty && !headerDirty) return;
    if (!actualIsOwner || !packId) return;
    try {
      const updated = await viewsApi.updatePack(packId, {
        name: packName.trim(),
        description: packDesc.trim(),
        widgets: editor.packWidgets,
        is_shared: packShared,
        row_columns: editor.rowColumns,
        row_descriptions: editor.rowDescriptions,
      });
      editor.markClean(updated);
    } catch {
      // silent
    }
  };

  const handleDelete = async () => {
    if (!packId || !confirm("Delete this pack?")) return;
    await viewsApi.deletePack(packId);
    navigate("/packs");
  };

  if (editor.loading) {
    return (
      <Layout>
        <div className="entity-page__loading">
          <div className="spinner" />
        </div>
      </Layout>
    );
  }

  if (editor.error || !editor.pack) {
    return (
      <Layout>
        <div className="pack-page">
          <Link to="/packs" className="entity-page__back">
            &larr; Back to Packs
          </Link>
          <div className="entity-page__error">
            {editor.error || "Pack not found"}
          </div>
        </div>
      </Layout>
    );
  }

  return (
    <Layout>
      <div className="pack-page">
        <Link to="/packs" className="entity-page__back">
          &larr; Back to Packs
        </Link>

        {/* Header */}
        <div className="pack-page__header">
          <div className="pack-page__header-left">
            {actualIsOwner && editingName ? (
              <input
                className="pack-page__name-input"
                value={packName}
                onChange={(e) => {
                  setPackName(e.target.value);
                  editor.markDirty();
                }}
                onBlur={() => setEditingName(false)}
                onKeyDown={(e) =>
                  e.key === "Enter" && setEditingName(false)
                }
                autoFocus
              />
            ) : (
              <h2
                className={
                  "pack-page__name" +
                  (actualIsOwner ? " pack-page__name--editable" : "")
                }
                onClick={() => actualIsOwner && setEditingName(true)}
                title={actualIsOwner ? "Click to edit" : undefined}
              >
                {packName}
              </h2>
            )}
            {actualIsOwner && editingDesc ? (
              <textarea
                className="pack-page__desc-input"
                value={packDesc}
                onChange={(e) => {
                  setPackDesc(e.target.value);
                  editor.markDirty();
                }}
                onBlur={() => setEditingDesc(false)}
                rows={2}
                autoFocus
              />
            ) : (
              <p
                className={
                  "pack-page__desc" +
                  (actualIsOwner ? " pack-page__desc--editable" : "")
                }
                onClick={() => actualIsOwner && setEditingDesc(true)}
                title={actualIsOwner ? "Click to edit" : undefined}
              >
                {packDesc || (actualIsOwner ? "Click to add description..." : "")}
              </p>
            )}
            <div className="pack-page__meta">
              <span>
                Owner: {editor.pack.owner_display_name || editor.pack.owner}
              </span>
              {actualIsOwner ? (
                <label className="pack-page__shared-toggle">
                  <input
                    type="checkbox"
                    checked={packShared}
                    onChange={(e) => {
                      setPackShared(e.target.checked);
                      editor.markDirty();
                    }}
                  />
                  Public
                </label>
              ) : (
                editor.pack.is_shared && (
                  <span className="pack-page__shared-badge">Shared</span>
                )
              )}
            </div>
          </div>
          <div className="pack-page__actions">
            {actualIsOwner && (editor.dirty || headerDirty) && (
              <button
                className="entity-page__action-btn entity-page__action-btn--primary"
                onClick={handleSave}
                disabled={editor.saving}
              >
                {editor.saving ? "Saving..." : "Save Pack"}
              </button>
            )}
            {actualIsOwner && (
              <button
                className="entity-page__action-btn entity-page__action-btn--danger"
                onClick={handleDelete}
              >
                Delete
              </button>
            )}
            <button
              className="entity-page__action-btn entity-page__action-btn--primary"
              onClick={() => setShowAlertDialog(true)}
            >
              Send Alert
            </button>
          </div>
        </div>

        <PackGrid editor={editor} />
      </div>

      {showAlertDialog && editor.pack && (
        <ScheduleEmailDialog
          entityType="pack"
          entityId={editor.pack.pack_id}
          widgets={editor.allResolvedWidgets}
          userEmail={user?.email}
          onSave={() => setShowAlertDialog(false)}
          onCancel={() => setShowAlertDialog(false)}
        />
      )}
    </Layout>
  );
}
