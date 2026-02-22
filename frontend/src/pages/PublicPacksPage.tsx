import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import type { AnalystPack } from "../types/entities";
import { Layout } from "../components/Layout";
import { ScheduleEmailDialog } from "../components/ScheduleEmailDialog";
import { PacksTable } from "../components/ag-grid/PacksTable";
import { useAuth } from "../auth/useAuth";
import * as viewsApi from "../config/viewsApi";
import "../styles/packs.css";

export function PublicPacksPage() {
  const [packs, setPacks] = useState<AnalystPack[]>([]);
  const [loading, setLoading] = useState(true);
  const { user } = useAuth();
  const navigate = useNavigate();
  const [alertPack, setAlertPack] = useState<AnalystPack | null>(null);

  useEffect(() => {
    viewsApi
      .listPacks()
      .then((all) => setPacks(all.filter((p) => p.is_shared)))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  return (
    <Layout>
      <div className="packs-list">
        <div className="packs-list__header">
          <h2>Public Packs</h2>
          <Link to="/packs" className="packs-list__create-btn">
            My Packs
          </Link>
        </div>
        {loading && (
          <div className="packs-list__loading">
            <div className="spinner" />
          </div>
        )}
        {!loading && packs.length === 0 && (
          <div className="packs-list__empty">
            No public packs available yet.
          </div>
        )}
        {!loading && packs.length > 0 && (
          <PacksTable
            packs={packs}
            showVisibility={false}
            showDelete={false}
            isOwner={(pack) => pack.owner === user?.username}
            onEdit={(pack) => navigate(`/pack/${pack.pack_id}`)}
            onSendAlert={(pack) => setAlertPack(pack)}
          />
        )}
      </div>

      {alertPack && (
        <ScheduleEmailDialog
          entityType="pack"
          entityId={alertPack.pack_id}
          userEmail={user?.email}
          onSave={() => setAlertPack(null)}
          onCancel={() => setAlertPack(null)}
        />
      )}
    </Layout>
  );
}
