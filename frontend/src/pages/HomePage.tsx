import { Link } from "react-router-dom";
import { Layout } from "../components/Layout";
import { SearchBar } from "../components/SearchBar";
import "../styles/layout.css";

export function HomePage() {
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
            <span className="browse-card__count">75 records</span>
          </Link>
          <Link to="/entity/dataset/people" className="browse-card">
            <span className="browse-card__category">contacts</span>
            <h3 className="browse-card__name">People</h3>
            <p className="browse-card__desc">
              Executives and analysts directory
            </p>
            <span className="browse-card__count">40 records</span>
          </Link>
          <Link to="/datasets" className="browse-card">
            <span className="browse-card__category">reference</span>
            <h3 className="browse-card__name">Datasets</h3>
            <p className="browse-card__desc">
              View all available datasets
            </p>
            <span className="browse-card__count">10 datasets</span>
          </Link>
        </div>
      </div>
    </Layout>
  );
}
