import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Layout } from "../components/Layout";
import { SearchBar } from "../components/SearchBar";
import api from "../config/api";
import "../styles/layout.css";

interface DatasetInfo {
  name: string;
  display_name: string;
  record_count: number;
  category: string;
}

export function HomePage() {
  const [datasets, setDatasets] = useState<DatasetInfo[]>([]);

  useEffect(() => {
    api
      .get<DatasetInfo[]>("/api/data/")
      .then((resp) => setDatasets(resp.data))
      .catch(() => {});
  }, []);

  const getCount = (name: string) => {
    const ds = datasets.find((d) => d.name === name);
    if (!ds) return null;
    const count = Number(ds.record_count);
    if (!count) return null;
    return count.toLocaleString();
  };

  const datasetCount = datasets.length;

  return (
    <Layout>
      <SearchBar />
      <div className="browse-section">
        <h3 className="browse-section__title">Browse</h3>
        <div className="browse-cards">
          <Link to="/entity/dataset/stocks" className="browse-card">
            <span className="browse-card__category">market_data</span>
            <h3 className="browse-card__name">Stocks</h3>
            <p className="browse-card__desc">
              Browse the full stock universe with fundamentals
            </p>
            {getCount("stocks") && (
              <span className="browse-card__count">
                {getCount("stocks")} records
              </span>
            )}
          </Link>
          <Link to="/entity/dataset/people" className="browse-card">
            <span className="browse-card__category">contacts</span>
            <h3 className="browse-card__name">People</h3>
            <p className="browse-card__desc">
              Corporate officers and executives directory
            </p>
            {getCount("people") && (
              <span className="browse-card__count">
                {getCount("people")} records
              </span>
            )}
          </Link>
          <Link to="/datasets" className="browse-card">
            <span className="browse-card__category">reference</span>
            <h3 className="browse-card__name">Datasets</h3>
            <p className="browse-card__desc">
              View all available datasets
            </p>
            {datasetCount > 0 && (
              <span className="browse-card__count">
                {datasetCount} datasets
              </span>
            )}
          </Link>
          <Link to="/packs/public" className="browse-card">
            <span className="browse-card__category">analyst</span>
            <h3 className="browse-card__name">Public Packs</h3>
            <p className="browse-card__desc">
              Browse shared analyst packs from your team
            </p>
          </Link>
          <Link to="/portfolios" className="browse-card">
            <span className="browse-card__category">portfolio</span>
            <h3 className="browse-card__name">Portfolios</h3>
            <p className="browse-card__desc">
              Portfolio positions, PnL, and exposure
            </p>
          </Link>
        </div>
      </div>
    </Layout>
  );
}
