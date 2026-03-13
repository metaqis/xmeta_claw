import { Navigate } from 'react-router-dom'
import { useAuthStore } from '../store/auth'

export function RequireAuth({ children }: { children: React.ReactNode }) {
  const token = useAuthStore((s) => s.token)
  if (!token) return <Navigate to="/login" replace />
  return <>{children}</>
}
