import { Routes, Route } from 'react-router-dom'
import Header from './components/Header.jsx'
import ProtectedRoute from './auth/ProtectedRoute.jsx'
import Home from './pages/Home.jsx'
import LoginPage from './pages/LoginPage.jsx'
import ForgotPasswordPage from './pages/ForgotPasswordPage.jsx'
import ResetPasswordPage from './pages/ResetPasswordPage.jsx'
import AdminPage from './pages/AdminPage.jsx'
import ProjectListPage from './pages/ProjectListPage.jsx'
import CommodityListPage from './pages/CommodityListPage.jsx'
import AnalysisListPage from './pages/AnalysisListPage.jsx'
import AnalysisDetailPage from './pages/AnalysisDetailPage.jsx'
import ProcessTypesPage from './pages/ProcessTypesPage.jsx'
import ToleranceMatrixPage from './pages/ToleranceMatrixPage.jsx'
import PostgresServicesPage from './pages/PostgresServicesPage.jsx'
import MinioServicesPage from './pages/MinioServicesPage.jsx'
import StandardTolerancesPage from './pages/StandardTolerancesPage.jsx'

// Nav: Project List -> Commodity List -> Analysis List -> Gap/Flush.
// A dropdown-based header nav (per the brief's UX section) is Phase 8;
// this is plain link-based navigation between the same pages.
function App() {
  return (
    <>
      <Header />
      <main>
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/login" element={<LoginPage />} />
          <Route path="/forgot-password" element={<ForgotPasswordPage />} />
          <Route path="/reset-password" element={<ResetPasswordPage />} />
          <Route
            path="/admin"
            element={
              <ProtectedRoute requireRootAdmin>
                <AdminPage />
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
            path="/projects/:projectId/analyses/:analysisId"
            element={
              <ProtectedRoute>
                <AnalysisDetailPage />
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
            path="/admin/process-types"
            element={
              <ProtectedRoute requireRootAdmin>
                <ProcessTypesPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/admin/process-types/:processTypeId/tolerance-matrix"
            element={
              <ProtectedRoute requireRootAdmin>
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
        </Routes>
      </main>
    </>
  )
}

export default App
