import { Routes, Route, Navigate } from 'react-router-dom'
import { AppShell } from '@/components/layout/app-shell'
import { AuthGuard } from '@/components/shared/auth-guard'
import { ErrorBoundary } from '@/components/shared/error-boundary'
import { LoginPage } from '@/pages/login-page'
import { DashboardPage } from '@/pages/dashboard-page'
import { BatchesPage } from '@/pages/batches-page'
import { BatchDetailPage } from '@/pages/batch-detail-page'
import { RotationReviewPage } from '@/pages/rotation-review-page'
import { DuplicateReviewPage } from '@/pages/duplicate-review-page'
import { CardLogPage } from '@/pages/card-log-page'
import { SettingsPage } from '@/pages/settings-page'

function ProtectedShell() {
  return (
    <AuthGuard>
      <AppShell />
    </AuthGuard>
  )
}

export default function App() {
  return (
    <ErrorBoundary>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route element={<ProtectedShell />}>
          <Route path="/" element={<DashboardPage />} />
          <Route path="/batches" element={<BatchesPage />} />
          <Route path="/batches/:id" element={<BatchDetailPage />} />
          <Route path="/rotation-review" element={<RotationReviewPage />} />
          <Route path="/duplicate-review" element={<DuplicateReviewPage />} />
          <Route path="/card-log" element={<CardLogPage />} />
          <Route path="/settings" element={<SettingsPage />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </ErrorBoundary>
  )
}
