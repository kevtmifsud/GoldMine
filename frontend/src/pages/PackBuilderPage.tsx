import { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { Layout } from "../components/Layout";
import * as viewsApi from "../config/viewsApi";
import "../styles/packs.css";

export function PackBuilderPage() {
  const navigate = useNavigate();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [isShared, setIsShared] = useState(false);
  const [saving, setSaving] = useState(false);

  const handleCreate = async () => {
    if (!name.trim()) return;
    setSaving(true);
    try {
      const created = await viewsApi.createPack({
        name: name.trim(),
        description: description.trim(),
        widgets: [],
        is_shared: isShared,
        row_columns: [2],
        row_heights: [],
        row_descriptions: [],
      });
      navigate(`/pack/${created.pack_id}`);
    } catch {
      // stay
    } finally {
      setSaving(false);
    }
  };

  return (
    <Layout>
      <div className="pack-builder">
        <Link to="/packs" className="entity-page__back">
          &larr; Back to Packs
        </Link>
        <h2>Create New Pack</h2>

        <div className="pack-builder__form">
          <div className="pack-builder__field">
            <label htmlFor="pack-name">Pack Name</label>
            <input
              id="pack-name"
              type="text"
              className="pack-builder__input"
              value={name}
              onChange={(e) => setName(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleCreate()}
              placeholder="My Research Pack"
              autoFocus
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

        <div className="pack-builder__footer">
          <button
            className="packs-list__create-btn"
            onClick={handleCreate}
            disabled={saving || !name.trim()}
          >
            {saving ? "Creating..." : "Create Pack"}
          </button>
        </div>
      </div>
    </Layout>
  );
}
