import { useState } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import { Layout } from "../components/Layout";
import { StudioGrid } from "../components/StudioGrid";
import { StudioChat } from "../components/StudioChat";
import { useAuth } from "../auth/useAuth";
import { useStudioEditor } from "../hooks/useStudioEditor";
import * as studiosApi from "../config/studiosApi";
import "../styles/studio.css";

export function StudioPage() {
  const { studioId } = useParams<{ studioId: string }>();
  const navigate = useNavigate();
  const { user } = useAuth();

  const editor = useStudioEditor(studioId ?? null, user?.username ?? null);

  // Header editing state
  const [editingName, setEditingName] = useState(false);
  const [nameValue, setNameValue] = useState("");
  const [nameInitialized, setNameInitialized] = useState(false);

  // Sync name from loaded studio
  if (editor.studio && !nameInitialized) {
    setNameValue(editor.studio.name);
    setNameInitialized(true);
  }

  const handleNameSave = async () => {
    setEditingName(false);
    if (!studioId || !editor.isOwner || !nameValue.trim()) return;
    if (nameValue.trim() === editor.studio?.name) return;
    try {
      await studiosApi.updateStudio(studioId, { name: nameValue.trim() });
      editor.updateStudioField({ name: nameValue.trim() });
    } catch {
      // revert
      if (editor.studio) setNameValue(editor.studio.name);
    }
  };

  const handleDelete = async () => {
    if (!studioId || !confirm("Delete this studio?")) return;
    await studiosApi.deleteStudio(studioId);
    navigate("/studios");
  };

  const handleSharedToggle = async (checked: boolean) => {
    if (!studioId || !editor.isOwner) return;
    // Optimistically update local state
    editor.updateStudioField({ is_shared: checked });
    try {
      await studiosApi.updateStudio(studioId, { is_shared: checked });
    } catch {
      // Revert on failure
      editor.updateStudioField({ is_shared: !checked });
    }
  };

  if (editor.loading) {
    return (
      <Layout contentClassName="studio-page-wrapper">
        <div className="studio-page">
          <div className="studio-page__toolbar">
            <Link to="/studios" className="studio-page__back">
              &larr; Studios
            </Link>
          </div>
          <div className="studio-page__body">
            <div className="studio-page__canvas" style={{ display: "flex", justifyContent: "center", alignItems: "center" }}>
              <div className="spinner" />
            </div>
          </div>
        </div>
      </Layout>
    );
  }

  if (editor.error || !editor.studio) {
    return (
      <Layout contentClassName="studio-page-wrapper">
        <div className="studio-page">
          <div className="studio-page__toolbar">
            <Link to="/studios" className="studio-page__back">
              &larr; Studios
            </Link>
          </div>
          <div className="studio-page__body">
            <div className="studio-page__canvas" style={{ display: "flex", justifyContent: "center", alignItems: "center" }}>
              <p>{editor.error || "Studio not found"}</p>
            </div>
          </div>
        </div>
      </Layout>
    );
  }

  return (
    <Layout contentClassName="studio-page-wrapper">
      <div className="studio-page">
        <div className="studio-page__toolbar">
          <Link to="/studios" className="studio-page__back">
            &larr; Studios
          </Link>

          {editor.isOwner && editingName ? (
            <input
              className="studio-page__name-input"
              value={nameValue}
              onChange={(e) => setNameValue(e.target.value)}
              onBlur={handleNameSave}
              onKeyDown={(e) => e.key === "Enter" && handleNameSave()}
              autoFocus
            />
          ) : (
            <span
              className="studio-page__name"
              onClick={() => {
                if (editor.isOwner) {
                  setEditingName(true);
                }
              }}
              title={editor.isOwner ? "Click to rename" : undefined}
            >
              {nameValue || editor.studio.name}
            </span>
          )}

          <span className="studio-page__toolbar-spacer" />

          <div className="studio-page__toolbar-meta">
            {editor.isOwner && (
              <label className="studio-page__shared-toggle">
                <input
                  type="checkbox"
                  checked={editor.studio.is_shared}
                  onChange={(e) => handleSharedToggle(e.target.checked)}
                />
                Public
              </label>
            )}
          </div>

          {editor.isOwner && editor.dirty && (
            <button
              className="studio-page__toolbar-btn studio-page__toolbar-btn--primary"
              onClick={editor.handleSave}
              disabled={editor.saving}
            >
              {editor.saving ? "Saving..." : "Save"}
            </button>
          )}

          {editor.isOwner && (
            <button
              className="studio-page__toolbar-btn studio-page__toolbar-btn--danger"
              onClick={handleDelete}
            >
              Delete
            </button>
          )}
        </div>

        <div className="studio-page__body">
          <div className="studio-page__canvas">
            <StudioGrid editor={editor} />
          </div>
          <div className="studio-page__sidebar">
            <StudioChat editor={editor} />
          </div>
        </div>
      </div>
    </Layout>
  );
}
