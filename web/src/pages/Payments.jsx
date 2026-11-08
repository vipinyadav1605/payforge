import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, money, when } from "../api.js";
import { ErrorBox, StatusBadge } from "../components.jsx";

export default function Payments() {
  const [rows, setRows] = useState([]);
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  async function load(after) {
    setLoading(true);
    try {
      const q = `/v1/payments?limit=10${after ? `&starting_after=${after}` : ""}`;
      const { data } = await api(q);
      setRows((r) => (after ? [...r, ...data.data] : data.data));
      setHasMore(data.has_more);
    } catch (e) {
      setError(e);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, []);

  return (
    <>
      <h1>Payments</h1>
      <ErrorBox error={error} />
      <table>
        <thead><tr><th>ID</th><th>Amount</th><th>Status</th><th>Method</th><th>Created</th></tr></thead>
        <tbody>
          {rows.map((p) => (
            <tr key={p.id}>
              <td><Link to={`/payments/${p.id}`}>{p.id}</Link></td>
              <td>{money(p.amount, p.currency)}</td>
              <td><StatusBadge status={p.status} />{p.failure_code && <small className="muted"> {p.failure_code}</small>}</td>
              <td>{p.payment_method}</td>
              <td>{when(p.created)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {hasMore && (
        <button disabled={loading} onClick={() => load(rows[rows.length - 1].id)}>
          {loading ? "Loading..." : "Load more"}
        </button>
      )}
    </>
  );
}
