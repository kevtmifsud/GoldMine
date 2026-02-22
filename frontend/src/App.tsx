import { useEffect } from "react";
import { Routes, Route, Navigate, useLocation } from "react-router-dom";
import { AuthProvider } from "./auth/AuthContext";
import { AuthGuard } from "./auth/AuthGuard";
import { LoginPage } from "./auth/LoginPage";
import { HomePage } from "./pages/HomePage";
import { EntityPage } from "./pages/EntityPage";
import { StockEntityPage } from "./pages/stock/StockEntityPage";
import { StockDetailsSubPage } from "./pages/stock/StockDetailsSubPage";
import { StockPortfolioSubPage } from "./pages/stock/StockPortfolioSubPage";
import { StockContactsSubPage } from "./pages/stock/StockContactsSubPage";
import { StockDataSubPage } from "./pages/stock/StockDataSubPage";
import { StockResearchSubPage } from "./pages/stock/StockResearchSubPage";
import { StockAlertsSubPage } from "./pages/stock/StockAlertsSubPage";
import { PacksListPage } from "./pages/PacksListPage";
import { PackPage } from "./pages/PackPage";
import { PackBuilderPage } from "./pages/PackBuilderPage";
import { DatasetsPage } from "./pages/DatasetsPage";
import { AlertsPage } from "./pages/AlertsPage";
import { PublicPacksPage } from "./pages/PublicPacksPage";

function ScrollToTop() {
  const { pathname } = useLocation();
  useEffect(() => {
    window.scrollTo(0, 0);
  }, [pathname]);
  return null;
}

function App() {
  return (
    <AuthProvider>
      <ScrollToTop />
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route
          path="/"
          element={
            <AuthGuard>
              <HomePage />
            </AuthGuard>
          }
        />
        <Route
          path="/entity/stock/:entityId"
          element={
            <AuthGuard>
              <StockEntityPage />
            </AuthGuard>
          }
        >
          <Route index element={<Navigate to="details" replace />} />
          <Route path="details" element={<StockDetailsSubPage />} />
          <Route path="portfolio" element={<StockPortfolioSubPage />} />
          <Route path="contacts" element={<StockContactsSubPage />} />
          <Route path="research" element={<StockResearchSubPage />} />
          <Route path="data" element={<StockDataSubPage />} />
          <Route path="alerts" element={<StockAlertsSubPage />} />
        </Route>
        <Route
          path="/entity/:entityType/:entityId"
          element={
            <AuthGuard>
              <EntityPage />
            </AuthGuard>
          }
        />
        <Route
          path="/datasets"
          element={
            <AuthGuard>
              <DatasetsPage />
            </AuthGuard>
          }
        />
        <Route
          path="/alerts"
          element={
            <AuthGuard>
              <AlertsPage />
            </AuthGuard>
          }
        />
        <Route
          path="/packs"
          element={
            <AuthGuard>
              <PacksListPage />
            </AuthGuard>
          }
        />
        <Route
          path="/packs/public"
          element={
            <AuthGuard>
              <PublicPacksPage />
            </AuthGuard>
          }
        />
        <Route
          path="/pack/new"
          element={
            <AuthGuard>
              <PackBuilderPage />
            </AuthGuard>
          }
        />
        <Route
          path="/pack/:packId"
          element={
            <AuthGuard>
              <PackPage />
            </AuthGuard>
          }
        />
        <Route
          path="/pack/:packId/edit"
          element={<Navigate to=".." replace />}
        />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </AuthProvider>
  );
}

export default App;
