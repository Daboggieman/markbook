import { Navigate, Outlet, Route, Routes } from "react-router";

import { useAuth } from "./auth/AuthContext";
import { AcademicPage } from "./pages/AcademicPage";
import { AssessmentsPage } from "./pages/AssessmentsPage";
import { DashboardPage } from "./pages/DashboardPage";
import { LoginPage } from "./pages/LoginPage";
import { ScoreSheetPage } from "./pages/ScoreSheetPage";
import { ShellPage } from "./pages/ShellPage";
import { StudentsPage } from "./pages/StudentsPage";
import { UsersPage } from "./pages/UsersPage";

function RequireAuth() {
  const { profile, booting } = useAuth();
  if (booting) return <p role="status">Signing in…</p>;
  if (!profile) return <Navigate to="/login" replace />;
  return <Outlet />;
}

/** Mirror of RequireAuth: a signed-in actor has no business on /login. */
function LoginRoute() {
  const { profile, booting } = useAuth();
  if (booting) return <p role="status">Signing in…</p>;
  if (profile) return <Navigate to="/" replace />;
  return <LoginPage />;
}

export function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<LoginRoute />} />
      <Route element={<RequireAuth />}>
        <Route path="/" element={<ShellPage />}>
          <Route index element={<DashboardPage />} />
          <Route path="academic" element={<AcademicPage />} />
          <Route path="students" element={<StudentsPage />} />
          <Route path="assessments" element={<AssessmentsPage />} />
          <Route path="assessments/:assessmentId/sheet" element={<ScoreSheetPage />} />
          <Route path="users" element={<UsersPage />} />
        </Route>
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
