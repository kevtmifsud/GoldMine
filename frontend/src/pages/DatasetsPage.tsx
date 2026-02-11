import { useEffect, useState } from "react";
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
        {!loading && (
          <div className="browse-cards">
            {datasets.map((ds) => (
              <Link
                key={ds.dataset_id}
                to={`/entity/dataset/${ds.name}`}
                className="browse-card"
              >
                <span className="browse-card__category">{ds.category}</span>
                <h3 className="browse-card__name">{ds.display_name}</h3>
                <p className="browse-card__desc">{ds.description}</p>
                <span className="browse-card__count">
                  {ds.record_count > 0
                    ? `${ds.record_count} records`
                    : "No data yet"}
                </span>
              </Link>
            ))}
          </div>
        )}
      </div>
    </Layout>
  );
}
