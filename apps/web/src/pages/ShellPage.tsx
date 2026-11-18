import { NavLink, Outlet, useNavigate } from "react-router";

import { hasPermission, useAuth } from "../auth/AuthContext";

interface NavItem {
  to: string;
  label: string;
  /** The permission that makes the item visible — UX filter only. */
  permission?: string;
}

const NAV_ITEMS: NavItem[] = [
  { to: "/", label: "Dashboard" },
  { to: "/academic", label: "Academic", permission: "academic.view" },
  { to: "/students", label: "Students", permission: "students.view" },
  { to: "/assessments", label: "Assessments", permission: "assessments.view" },
  { to: "/users", label: "Users", permission: "users.view" },
  { to: "/reports", label: "Reports", permission: "reports.view" },
];

export function ShellPage() {
  const { profile, logout } = useAuth();
  const navigate = useNavigate();

  const visible = NAV_ITEMS.filter((item) => !item.permission || hasPermission(profile, item.permission));

  return (
    <div className="app-shell">
      <nav className="app-nav" aria-label="Main">
        <ul>
          {visible.map((item) => (
            <li key={item.to}>
              <NavLink to={item.to} end={item.to === "/"}>
                {item.label}
              </NavLink>
            </li>
          ))}
        </ul>
      </nav>
      <main className="app-main">
        <header style={{ display: "flex", justifyContent: "space-between" }}>
          <p>
            {profile?.username} · {profile?.email}
          </p>
          <button
            type="button"
            onClick={async () => {
              await logout();
              navigate("/login");
            }}
          >
            Sign out
          </button>
        </header>
        <Outlet />
      </main>
    </div>
  );
}
