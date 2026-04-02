import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import type { AnalystPack } from "../types/entities";
import { Layout } from "../components/Layout";
import { ScheduleEmailDialog } from "../components/ScheduleEmailDialog";
import { PacksTable } from "../components/ag-grid/PacksTable";
import { useAuth } from "../auth/useAuth";
import * as viewsApi from "../config/viewsApi";
import "../styles/packs.css";

export function PacksListPage() {
  const [packs, setPacks] = useState<AnalystPack[]>([]);
  const [loading, setLoading] = useState(true);
  const { user } = useAuth();
  const navigate = useNavigate();

  // Send-alert dialog state
  const [alertPack, setAlertPack] = useState<AnalystPack | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  const loadPacks = () => {
    setLoading(true);
    viewsApi
      .listPacks()
      .then(setPacks)
      .catch(() => {})
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    loadPacks();
  }, []);

  const handleDelete = async (pack: AnalystPack) => {
    if (!confirm(`Delete pack "${pack.name}"?`)) return;
    setDeletingId(pack.pack_id);
    try {
      await viewsApi.deletePack(pack.pack_id);
      setPacks((prev) => prev.filter((p) => p.pack_id !== pack.pack_id));
    } catch {
      // stay
    } finally {
      setDeletingId(null);
    }
  };

  const isOwner = (pack: AnalystPack) => pack.owner === user?.username;

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
          <span className="packs-list__chat-hint">
            Type <code>/pack</code> in chat to generate from conversation
          </span>
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
          <PacksTable
            packs={packs}
            isOwner={isOwner}
            onEdit={(pack) => navigate(`/pack/${pack.pack_id}`)}
            onDelete={handleDelete}
            onSendAlert={(pack) => setAlertPack(pack)}
            deletingId={deletingId}
          />
        )}
      </div>

      {alertPack && (
        <ScheduleEmailDialog
          entityType="pack"
          entityId={alertPack.pack_id}
          userEmail={user?.email}
          onSave={() => {
            setAlertPack(null);
            loadPacks();
          }}
          onCancel={() => setAlertPack(null)}
        />
      )}
    </Layout>
  );
}
