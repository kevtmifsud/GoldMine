import { useEffect } from "react";
import { Routes, Route, Navigate, useLocation } from "react-router-dom";
import { AuthProvider } from "./auth/AuthContext";
import { AuthGuard } from "./auth/AuthGuard";
import { LoginPage } from "./auth/LoginPage";
import { HomePage } from "./pages/HomePage";
import { EntityPage } from "./pages/EntityPage";
import { PacksListPage } from "./pages/PacksListPage";
import { PackPage } from "./pages/PackPage";
import { PackBuilderPage } from "./pages/PackBuilderPage";
import { DatasetsPage } from "./pages/DatasetsPage";
import { AlertsPage } from "./pages/AlertsPage";

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
          element={
            <AuthGuard>
              <PackBuilderPage />
            </AuthGuard>
          }
        />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </AuthProvider>
  );
}

export default App;
