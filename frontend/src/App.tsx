import { useEffect } from "react";
import { Routes, Route, Navigate, useLocation } from "react-router-dom";
import { AuthProvider } from "./auth/AuthContext";
import { GlobalChatProvider } from "./context/GlobalChatContext";
import { AuthGuard } from "./auth/AuthGuard";
import { LoginPage } from "./auth/LoginPage";
import { HomePage } from "./pages/HomePage";
import { EntityPage } from "./pages/EntityPage";
import { StockEntityPage } from "./pages/stock/StockEntityPage";
import { StockDetailsSubPage } from "./pages/stock/StockDetailsSubPage";
import { StockPortfolioSubPage } from "./pages/stock/StockPortfolioSubPage";
import { StockContactsSubPage } from "./pages/stock/StockContactsSubPage";
import { StockDataSubPage } from "./pages/stock/StockDataSubPage";
import { StockAlertsSubPage } from "./pages/stock/StockAlertsSubPage";
import { StockPackSubPage } from "./pages/stock/StockPackSubPage";
import { StockResearchLayout } from "./pages/stock/research/StockResearchLayout";
import { ResearchSummarySubPage } from "./pages/stock/research/ResearchSummarySubPage";
import { ResearchCategorySubPage } from "./pages/stock/research/ResearchCategorySubPage";
import { SecFilingsSubPage } from "./pages/stock/research/SecFilingsSubPage";
import { TranscriptsSubPage } from "./pages/stock/research/TranscriptsSubPage";
import { StockFundamentalsLayout } from "./pages/stock/fundamentals/StockFundamentalsLayout";
import { FundamentalsSummarySubPage } from "./pages/stock/fundamentals/FundamentalsSummarySubPage";
import { IncomeStatementSubPage } from "./pages/stock/fundamentals/IncomeStatementSubPage";
import { BalanceSheetSubPage } from "./pages/stock/fundamentals/BalanceSheetSubPage";
import { CashFlowSubPage } from "./pages/stock/fundamentals/CashFlowSubPage";
import { PacksListPage } from "./pages/PacksListPage";
import { PackPage } from "./pages/PackPage";
import { PackBuilderPage } from "./pages/PackBuilderPage";
import { DatasetsPage } from "./pages/DatasetsPage";
import { AlertsPage } from "./pages/AlertsPage";
import { ReportsPage } from "./pages/ReportsPage";
import { PublicPacksPage } from "./pages/PublicPacksPage";
import { PortfoliosPage } from "./pages/PortfoliosPage";
import { EarningsPreviewPage } from "./pages/EarningsPreviewPage";
import { ChatPage } from "./pages/ChatPage";
import { ChatHistoryPage } from "./pages/ChatHistoryPage";
import { ChatDetailPage } from "./pages/ChatDetailPage";

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
      <GlobalChatProvider>
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
          <Route index element={<Navigate to="portfolio" replace />} />
          <Route path="details" element={<StockDetailsSubPage />} />
          <Route path="portfolio" element={<StockPortfolioSubPage />} />
          <Route path="contacts" element={<StockContactsSubPage />} />
          <Route path="research" element={<StockResearchLayout />}>
            <Route index element={<ResearchSummarySubPage />} />
            <Route
              path="transcripts"
              element={<TranscriptsSubPage />}
            />
            <Route
              path="filings"
              element={<SecFilingsSubPage />}
            />
            <Route
              path="sellside"
              element={
                <ResearchCategorySubPage
                  title="Sell-side Research"
                  docTypeFilter={["report"]}
                  uploadAccept=".pdf"
                />
              }
            />
            <Route
              path="data-files"
              element={
                <ResearchCategorySubPage
                  title="Misc Data Files"
                  docTypeFilter={["data_export"]}
                  uploadAccept=".csv,.txt"
                />
              }
            />
            <Route
              path="notes"
              element={
                <ResearchCategorySubPage
                  title="Notes"
                  docTypeFilter={["notes"]}
                  uploadAccept=".pdf"
                />
              }
            />
            <Route
              path="other"
              element={
                <ResearchCategorySubPage
                  title="Other Documents"
                  excludeDocTypes={["audio", "transcript", "report", "data_export", "notes", "sec_filing"]}
                />
              }
            />
          </Route>
          <Route path="fundamentals" element={<StockFundamentalsLayout />}>
            <Route index element={<FundamentalsSummarySubPage />} />
            <Route path="income-statement" element={<IncomeStatementSubPage />} />
            <Route path="balance-sheet" element={<BalanceSheetSubPage />} />
            <Route path="cash-flow" element={<CashFlowSubPage />} />
          </Route>
          <Route path="data" element={<StockDataSubPage />} />
          <Route path="alerts" element={<StockAlertsSubPage />} />
          <Route path="pack" element={<StockPackSubPage />} />
        </Route>
        <Route
          path="/portfolios"
          element={
            <AuthGuard>
              <PortfoliosPage />
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
          path="/reports"
          element={
            <AuthGuard>
              <ReportsPage />
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
        <Route
          path="/earnings"
          element={
            <AuthGuard>
              <EarningsPreviewPage />
            </AuthGuard>
          }
        />
        <Route
          path="/chat"
          element={
            <AuthGuard>
              <ChatPage />
            </AuthGuard>
          }
        />
        <Route
          path="/chat/history"
          element={
            <AuthGuard>
              <ChatHistoryPage />
            </AuthGuard>
          }
        />
        <Route
          path="/chat/history/:conversationId"
          element={
            <AuthGuard>
              <ChatDetailPage />
            </AuthGuard>
          }
        />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
      </GlobalChatProvider>
    </AuthProvider>
  );
}

export default App;
