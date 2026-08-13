import { Routes, Route } from 'react-router-dom'
import Header from './components/Header.jsx'
import Banner from './components/Banner.jsx'
import ProtectedRoute from './auth/ProtectedRoute.jsx'
import Home from './pages/Home.jsx'
import LoginPage from './pages/LoginPage.jsx'
import ForgotPasswordPage from './pages/ForgotPasswordPage.jsx'
import ResetPasswordPage from './pages/ResetPasswordPage.jsx'
import SetPasswordPage from './pages/SetPasswordPage.jsx'
import SecuritySettingsPage from './pages/SecuritySettingsPage.jsx'
import AdminPage from './pages/AdminPage.jsx'
import ClientsPage from './pages/ClientsPage.jsx'
import ClientAdminPage from './pages/ClientAdminPage.jsx'
import ProjectListPage from './pages/ProjectListPage.jsx'
import CommodityListPage from './pages/CommodityListPage.jsx'
import AnalysisListPage from './pages/AnalysisListPage.jsx'
import AnalysisDetailPage from './pages/AnalysisDetailPage.jsx'
import AnalysisReportPage from './pages/AnalysisReportPage.jsx'
import CommodityReportPage from './pages/CommodityReportPage.jsx'
import ProcessTypesPage from './pages/ProcessTypesPage.jsx'
import ToleranceMatrixPage from './pages/ToleranceMatrixPage.jsx'
import PostgresServicesPage from './pages/PostgresServicesPage.jsx'
import MinioServicesPage from './pages/MinioServicesPage.jsx'
import PostgresServersPage from './pages/PostgresServersPage.jsx'
import MinioServersPage from './pages/MinioServersPage.jsx'
import StandardTolerancesPage from './pages/StandardTolerancesPage.jsx'
import LogsPage from './pages/LogsPage.jsx'
import BannerPage from './pages/BannerPage.jsx'
import AngledInterfaceHelpPage from './pages/AngledInterfaceHelpPage.jsx'
import StatisticalModelPage from './pages/StatisticalModelPage.jsx'
import StatisticalModelHelpPage from './pages/StatisticalModelHelpPage.jsx'

// Nav: Project List -> Commodity List -> Analysis List -> Gap/Flush.
// A dropdown-based header nav (per the brief's UX section) is Phase 8;
// this is plain link-based navigation between the same pages.
function App() {
  return (
    <>
      <Header />
      {/* Above <main> so it sits over every page. Renders nothing unless
          a banner is active and this user hasn't dismissed it. */}
      <Banner />
      <main>
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/login" element={<LoginPage />} />
          <Route path="/forgot-password" element={<ForgotPasswordPage />} />
          <Route path="/reset-password" element={<ResetPasswordPage />} />
          <Route path="/set-password" element={<SetPasswordPage />} />
          <Route
            path="/admin"
            element={
              <ProtectedRoute requireRootAdmin>
                <AdminPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/admin/clients"
            element={
              <ProtectedRoute requireRootAdmin>
                <ClientsPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/client-admin"
            element={
              <ProtectedRoute requireClientAdmin>
                <ClientAdminPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/projects"
            element={
              <ProtectedRoute>
                <ProjectListPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/projects/:projectId/commodities"
            element={
              <ProtectedRoute>
                <CommodityListPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/projects/:projectId/commodities/:commodityId/analyses"
            element={
              <ProtectedRoute>
                <AnalysisListPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/projects/:projectId/commodities/:commodityId/report"
            element={
              <ProtectedRoute>
                <CommodityReportPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/projects/:projectId/analyses/:analysisId"
            element={
              <ProtectedRoute>
                <AnalysisDetailPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/projects/:projectId/analyses/:analysisId/report/:entryType"
            element={
              <ProtectedRoute>
                <AnalysisReportPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/projects/:projectId/standard-tolerances"
            element={
              <ProtectedRoute>
                <StandardTolerancesPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/help/angled-interface"
            element={
              <ProtectedRoute>
                <AngledInterfaceHelpPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/help/statistical-model"
            element={
              <ProtectedRoute>
                <StatisticalModelHelpPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/client-admin/statistical-model"
            element={
              <ProtectedRoute requireClientAdmin>
                <StatisticalModelPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/client-admin/process-types"
            element={
              <ProtectedRoute requireClientAdmin>
                <ProcessTypesPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/client-admin/process-types/:processTypeId/tolerance-matrix"
            element={
              <ProtectedRoute requireClientAdmin>
                <ToleranceMatrixPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/admin/postgres-services"
            element={
              <ProtectedRoute requireRootAdmin>
                <PostgresServicesPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/admin/minio-services"
            element={
              <ProtectedRoute requireRootAdmin>
                <MinioServicesPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/admin/postgres-servers"
            element={
              <ProtectedRoute requireRootAdmin>
                <PostgresServersPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/admin/minio-servers"
            element={
              <ProtectedRoute requireRootAdmin>
                <MinioServersPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/admin/banner"
            element={
              <ProtectedRoute requireRootAdmin>
                <BannerPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/admin/logs"
            element={
              <ProtectedRoute requireRootAdmin>
                <LogsPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/admin/security"
            element={
              <ProtectedRoute requireRootAdmin>
                <SecuritySettingsPage />
              </ProtectedRoute>
            }
          />
        </Routes>
      </main>
    </>
  )
}

export default App
