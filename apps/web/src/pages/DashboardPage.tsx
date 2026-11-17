import { useAuth } from "../auth/AuthContext";

export function DashboardPage() {
  const { profile } = useAuth();
  return (
    <section>
      <h2>Dashboard</h2>
      <p>
        Signed in as <strong>{profile?.email}</strong> with{" "}
        {profile?.effective_permissions.length ?? 0} effective permissions.
      </p>
      <p>Screens for this phase land incrementally: assessments, score sheets, review, reports.</p>
    </section>
  );
}
