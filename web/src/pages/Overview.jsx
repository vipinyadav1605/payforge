import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, money, when } from "../api.js";
import { ErrorBox, StatusBadge } from "../components.jsx";

export default function Overview() {
  const [balance, setBalance] = useState(null);
  const [recent, setRecent] = useState([]);
  const [error, setError] = useState(null);

  useEffect(() => {
    Promise.all([api("/v1/balance"), api("/v1/payments?limit=5")])
      .then(([b, p]) => {
        setBalance(b.data.available);
        setRecent(p.data.data);
      })
      .catch(setError);
  }, []);

  const entries = balance ? Object.entries(balance) : [];
  return (
    <>
      <h1>Overview</h1>
      <ErrorBox error={error} />
      <div className="cards">
        {entries.length === 0 && <div className="card stat"><span className="muted">Balance</span><strong>$0.00</strong></div>}
        {entries.map(([cur, amount]) => (
          <div className="card stat" key={cur}>
            <span className="muted">Available balance ({cur.toUpperCase()})</span>
            <strong>{money(amount, cur)}</strong>
            <small className="muted">from the double-entry ledger</small>
          </div>
        ))}
      </div>

      <h2>Recent payments</h2>
      <table>
        <thead><tr><th>ID</th><th>Amount</th><th>Status</th><th>Created</th></tr></thead>
        <tbody>
          {recent.map((p) => (
            <tr key={p.id}>
              <td><Link to={`/payments/${p.id}`}>{p.id}</Link></td>
              <td>{money(p.amount, p.currency)}</td>
              <td><StatusBadge status={p.status} /></td>
              <td>{when(p.created)}</td>
            </tr>
          ))}
          {recent.length === 0 && <tr><td colSpan="4" className="muted">No payments yet. Try “New test payment”.</td></tr>}
        </tbody>
      </table>
    </>
  );
}
