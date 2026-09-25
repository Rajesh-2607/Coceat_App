import { useQuery } from "@tanstack/react-query";
import { api, unwrap } from "../api/client";
import { ErrorText, Loading } from "../lib/ui";

/** Platform admin console. Setup queue, subscriptions and vertical config come next. */
export function AdminApp() {
  const businesses = useQuery({
    queryKey: ["admin", "businesses"],
    queryFn: async () => unwrap(await api.GET("/api/admin/businesses")),
  });
  return (
    <main className="mx-auto max-w-4xl space-y-4 p-6">
      <h1 className="text-2xl font-bold">Cocreat Admin</h1>
      {businesses.isPending ? (
        <Loading />
      ) : businesses.error ? (
        <ErrorText error={businesses.error} />
      ) : (
        <table className="w-full text-left">
          <thead>
            <tr className="border-b">
              <th className="py-2">Business</th>
              <th>Vertical</th>
              <th>GSTIN</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {businesses.data.map((b) => (
              <tr key={b.id} className="border-b">
                <td className="py-2">{b.name}</td>
                <td>{b.vertical_key}</td>
                <td>{b.gstin ?? "—"}</td>
                <td>{b.status}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </main>
  );
}
