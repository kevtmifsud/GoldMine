import { useState, useEffect, useCallback } from "react";
import { listPacks, createPack, updatePack, getPack } from "../../config/viewsApi";
import type { AddToPackConfig } from "./ChatMarkdown";
import type { AnalystPack, MCPTileRef } from "../../types/entities";
import "../../styles/chat.css";

interface AddToPackModalProps {
  isOpen: boolean;
  onClose: () => void;
  tileConfig: AddToPackConfig | null;
}

/** @deprecated Use AddToPackModalProps */
export type AddToPageModalProps = AddToPackModalProps;

export function AddToPageModal({
  isOpen,
  onClose,
  tileConfig,
}: AddToPackModalProps) {
  const [packs, setPacks] = useState<AnalystPack[]>([]);
  const [loading, setLoading] = useState(false);
  const [selectedPackId, setSelectedPackId] = useState<string>("");
  const [newTitle, setNewTitle] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<{
    packName: string;
    packId: string;
  } | null>(null);

  const loadPacks = useCallback(async () => {
    setLoading(true);
    try {
      const data = await listPacks();
      setPacks(data);
    } catch {
      setPacks([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (isOpen) {
      loadPacks();
      setNewTitle("");
      setSelectedPackId("");
      setError(null);
      setSuccess(null);
    }
  }, [isOpen, loadPacks]);

  useEffect(() => {
    if (!isOpen) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [isOpen, onClose]);

  if (!isOpen || !tileConfig) return null;

  const buildTile = (): MCPTileRef => {
    const titleText =
      (tileConfig.chartOption?.title as Record<string, unknown>)?.text as string ||
      tileConfig.tool ||
      "Tile";

    const hasChart = tileConfig.chartOption && Object.keys(tileConfig.chartOption).length > 0;

    return {
      tile_id: crypto.randomUUID(),
      title: titleText,
      tool: tileConfig.tool,
      params: tileConfig.params,
      display_type: hasChart ? "plotly_line" : "ag_grid",
      // Don't save ECharts option — MCP server provides chart_config at execution time
      chart_config: null,
      is_template: false,
      row: 0,
      col: 0,
    };
  };

  const addTileToPack = async (packId: string) => {
    const pack = await getPack(packId);
    const tile = buildTile();

    // Find next empty cell
    const occupied = new Set([
      ...(pack.widgets || []).map((w) => `${w.row}-${w.col}`),
      ...(pack.mcp_tiles || []).map((t) => `${t.row}-${t.col}`),
    ]);
    let found = false;
    for (let r = 0; r < pack.row_columns.length && !found; r++) {
      for (let c = 0; c < pack.row_columns[r] && !found; c++) {
        if (!occupied.has(`${r}-${c}`)) {
          tile.row = r;
          tile.col = c;
          found = true;
        }
      }
    }
    if (!found) {
      tile.row = pack.row_columns.length;
      tile.col = 0;
    }

    const updatedTiles = [...(pack.mcp_tiles || []), tile];
    const updatedRowCols = !found ? [...pack.row_columns, 2] : pack.row_columns;
    await updatePack(packId, { mcp_tiles: updatedTiles, row_columns: updatedRowCols });
  };

  const handleCreateNew = async () => {
    if (!newTitle.trim()) return;
    setSaving(true);
    setError(null);
    try {
      const tile = buildTile();
      const pack = await createPack({
        name: newTitle.trim(),
        description: "",
        widgets: [],
        mcp_tiles: [tile],
        is_shared: false,
        row_columns: [2],
        row_heights: [],
        row_descriptions: [],
      });
      setSuccess({ packName: pack.name, packId: pack.pack_id });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create pack");
    } finally {
      setSaving(false);
    }
  };

  const handleAddToExisting = async (pack: AnalystPack) => {
    setSaving(true);
    setError(null);
    try {
      await addTileToPack(pack.pack_id);
      setSuccess({ packName: pack.name, packId: pack.pack_id });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to add tile");
    } finally {
      setSaving(false);
    }
  };

  const tileCount = (pack: AnalystPack) =>
    (pack.widgets?.length || 0) + (pack.mcp_tiles?.length || 0);

  return (
    <div className="add-to-page__overlay" onClick={onClose}>
      <div
        className="add-to-page__dialog"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="add-to-page__header">
          <h3>Add to pack</h3>
          <button className="add-to-page__close" onClick={onClose}>
            &times;
          </button>
        </div>

        {success ? (
          <div className="add-to-page__success">
            <p>
              Added to <strong>{success.packName}</strong>
            </p>
            <div className="add-to-page__success-actions">
              <a href={`/pack/${success.packId}`} className="add-to-page__link">
                View Pack
              </a>
              <button className="add-to-page__btn" onClick={onClose}>
                Done
              </button>
            </div>
          </div>
        ) : (
          <div className="add-to-page__body">
            <div className="add-to-page__section">
              <div className="add-to-page__new-row">
                <input
                  className="add-to-page__input"
                  type="text"
                  placeholder="New pack name..."
                  value={newTitle}
                  onChange={(e) => setNewTitle(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") handleCreateNew();
                  }}
                  disabled={saving}
                  autoFocus
                />
                <button
                  className="add-to-page__btn add-to-page__btn--primary"
                  onClick={handleCreateNew}
                  disabled={!newTitle.trim() || saving}
                >
                  {saving ? "Creating..." : "Create & Add"}
                </button>
              </div>
            </div>

            {packs.length > 0 && (
              <>
                <div className="add-to-page__divider">
                  or add to existing pack
                </div>
                <div className="add-to-page__select-row">
                  {loading ? (
                    <div className="add-to-page__loading">Loading...</div>
                  ) : (
                    <>
                      <select
                        className="add-to-page__select"
                        value={selectedPackId}
                        onChange={(e) => setSelectedPackId(e.target.value)}
                        disabled={saving}
                      >
                        <option value="">Select existing pack...</option>
                        {packs.map((pack) => (
                          <option key={pack.pack_id} value={pack.pack_id}>
                            {pack.name} ({tileCount(pack)} tile{tileCount(pack) !== 1 ? "s" : ""})
                          </option>
                        ))}
                      </select>
                      <button
                        className="add-to-page__btn add-to-page__btn--primary"
                        onClick={() => {
                          const pack = packs.find((p) => p.pack_id === selectedPackId);
                          if (pack) handleAddToExisting(pack);
                        }}
                        disabled={!selectedPackId || saving}
                      >
                        {saving ? "Adding..." : "Add"}
                      </button>
                    </>
                  )}
                </div>
              </>
            )}

            {error && (
              <div className="add-to-page__error">{error}</div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
