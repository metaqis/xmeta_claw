import { RouteObject, Navigate } from 'react-router-dom'
import MainLayout from '../layouts/MainLayout'
import { RequireAuth } from '../components/RequireAuth'
import LoginPage from '../pages/login'
import DashboardPage from '../pages/dashboard'
import CalendarPage from '../pages/calendar'
import ArchivesPage from '../pages/archives'
import ArchiveDetailPage from '../pages/archives/Detail'
import IPsPage from '../pages/ips'
import IPArchivesPage from '../pages/ips/Archives'
import TasksPage from '../pages/tasks'

export const routes: RouteObject[] = [
  { path: '/login', element: <LoginPage /> },
  {
    path: '/',
    element: (
      <RequireAuth>
        <MainLayout />
      </RequireAuth>
    ),
    children: [
      { index: true, element: <Navigate to="/dashboard" replace /> },
      { path: 'dashboard', element: <DashboardPage /> },
      { path: 'calendar', element: <CalendarPage /> },
      { path: 'archives', element: <ArchivesPage /> },
      { path: 'archives/:id', element: <ArchiveDetailPage /> },
      { path: 'ips', element: <IPsPage /> },
      { path: 'ips/:id/archives', element: <IPArchivesPage /> },
      { path: 'tasks', element: <TasksPage /> },
    ],
  },
  { path: '*', element: <Navigate to="/dashboard" replace /> },
]
