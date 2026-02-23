import { useEffect, useState, useMemo } from "react";
import { Link } from "react-router-dom";
import api from "../config/api";
import { Layout } from "../components/Layout";
import "../styles/entity.css";

interface DatasetInfo {
  dataset_id: string;
  name: string;
  display_name: string;
  description: string;
  record_count: number;
  id_field: string;
  category: string;
}

const CATEGORY_ORDER = [
  "market_data",
  "research",
  "contacts",
  "compliance",
  "portfolio",
  "reference",
];

const CATEGORY_LABELS: Record<string, string> = {
  market_data: "Market Data",
  research: "Research",
  compliance: "Compliance",
  contacts: "Contacts",
  portfolio: "Portfolio",
  reference: "Reference",
};

export function DatasetsPage() {
  const [datasets, setDatasets] = useState<DatasetInfo[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api
      .get<DatasetInfo[]>("/api/data/")
      .then((resp) => setDatasets(resp.data))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const grouped = useMemo(() => {
    const groups: { category: string; label: string; items: DatasetInfo[] }[] =
      [];
    const byCategory = new Map<string, DatasetInfo[]>();
    for (const ds of datasets) {
      const cat = ds.category || "other";
      if (!byCategory.has(cat)) byCategory.set(cat, []);
      byCategory.get(cat)!.push(ds);
    }
    // Ordered categories first, then any remaining
    const seen = new Set<string>();
    for (const cat of CATEGORY_ORDER) {
      if (byCategory.has(cat)) {
        groups.push({
          category: cat,
          label: CATEGORY_LABELS[cat] || cat,
          items: byCategory.get(cat)!,
        });
        seen.add(cat);
      }
    }
    for (const [cat, items] of byCategory) {
      if (!seen.has(cat)) {
        groups.push({
          category: cat,
          label: CATEGORY_LABELS[cat] || cat,
          items,
        });
      }
    }
    return groups;
  }, [datasets]);

  return (
    <Layout>
      <div className="entity-page">
        <Link to="/" className="entity-page__back">
          &larr; Back to Search
        </Link>
        <h2 className="browse-section__title">All Datasets</h2>
        {loading && (
          <div className="entity-page__loading">
            <div className="spinner" />
          </div>
        )}
        {!loading &&
          grouped.map((group) => (
            <div key={group.category} className="browse-section__group">
              <h3 className="browse-section__group-title">{group.label}</h3>
              <div className="browse-cards">
                {group.items.map((ds) => (
                  <Link
                    key={ds.dataset_id}
                    to={`/entity/dataset/${ds.name}`}
                    className="browse-card"
                  >
                    <span className="browse-card__category">
                      {ds.category}
                    </span>
                    <h3 className="browse-card__name">{ds.display_name}</h3>
                    <p className="browse-card__desc">{ds.description}</p>
                    <span className="browse-card__count">
                      {Number(ds.record_count) > 0
                        ? `${Number(ds.record_count).toLocaleString()} records`
                        : "No data yet"}
                    </span>
                  </Link>
                ))}
              </div>
            </div>
          ))}
      </div>
    </Layout>
  );
}
