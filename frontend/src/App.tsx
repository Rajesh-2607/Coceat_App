import { Navigate, Route, Routes } from "react-router-dom";
import { AdminApp } from "./admin/AdminApp";
import { ApiError } from "./api/client";
import { useMe } from "./api/hooks";
import { LoginPage } from "./auth/LoginPage";
import { ErrorText, Loading } from "./lib/ui";
import { WorkspaceApp } from "./workspace/WorkspaceApp";

export function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/w/*" element={<Authenticated area="workspace" />} />
      <Route path="/admin/*" element={<Authenticated area="admin" />} />
      <Route path="*" element={<Navigate to="/w" replace />} />
    </Routes>
  );
}

function Authenticated({ area }: { area: "workspace" | "admin" }) {
  const me = useMe();
  if (me.isPending) return <Loading />;
  if (me.error instanceof ApiError && me.error.status === 401) return <Navigate to="/login" replace />;
  if (me.error) return <ErrorText error={me.error} />;
  if (area === "admin") return me.data.is_platform_admin ? <AdminApp /> : <Navigate to="/w" replace />;
  return <WorkspaceApp me={me.data} />;
}
