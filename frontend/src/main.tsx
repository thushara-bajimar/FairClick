import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import Layout from './components/Layout'
import './index.css'
import Dashboard from './pages/Dashboard'
import EvidenceVault from './pages/EvidenceVault'
import Landing from './pages/Landing'
import NewTask from './pages/NewTask'
import Reports from './pages/Reports'
import SettingsPage from './pages/Settings'
import Workspace, { WorkspaceIndex } from './pages/Workspace'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Landing />} />
        <Route path="/app" element={<Layout />}>
          <Route index element={<Dashboard />} />
          <Route path="new" element={<NewTask />} />
          <Route path="workspace" element={<WorkspaceIndex />} />
          <Route path="sessions/:sessionId" element={<Workspace />} />
          <Route path="evidence" element={<EvidenceVault />} />
          <Route path="reports" element={<Reports />} />
          <Route path="settings" element={<SettingsPage />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  </StrictMode>,
)
