import { useState } from "react";
import { Link } from "react-router-dom";
import { api, money, newIdempotencyKey } from "../api.js";
import { ErrorBox } from "../components.jsx";

const METHODS = [
  ["pm_card_visa", "Visa (approved)"],
  ["pm_card_declined", "Card declined"],
  ["pm_card_insufficient_funds", "Insufficient funds"],
  ["pm_card_expired", "Expired card"],
];

export default function NewPayment() {
  const [amount, setAmount] = useState("100.00");
  const [currency, setCurrency] = useState("usd");
  const [method, setMethod] = useState("pm_card_visa");
  const [capture, setCapture] = useState(true);
  const [description, setDescription] = useState("");
  const [results, setResults] = useState([]);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  const body = () => ({
    amount: Math.round(parseFloat(amount) * 100),
    currency,
    payment_method: method,
    capture,
    ...(description ? { description } : {}),
  });

  async function send(times) {
    setBusy(true);
    setError(null);
    const key = newIdempotencyKey(); // the SAME key for every attempt below
    const out = [];
    try {
      for (let i = 1; i <= times; i++) {
        const r = await api("/v1/payments", { method: "POST", body: body(), idempotencyKey: key });
        out.push({ attempt: i, key, status: r.status, replayed: r.headers.get("Idempotent-Replayed") === "true", payment: r.data });
      }
    } catch (e) {
      setError(e);
    } finally {
      setResults(out);
      setBusy(false);
    }
  }

  return (
    <>
      <h1>New test payment</h1>
      <div className="card form">
        <label>Amount <input type="number" step="0.01" min="0.01" value={amount} onChange={(e) => setAmount(e.target.value)} /></label>
        <label>Currency
          <select value={currency} onChange={(e) => setCurrency(e.target.value)}>
            {["usd", "inr", "eur", "gbp"].map((c) => <option key={c} value={c}>{c.toUpperCase()}</option>)}
          </select>
        </label>
        <label>Payment method (mock PSP)
          <select value={method} onChange={(e) => setMethod(e.target.value)}>
            {METHODS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
        </label>
        <label>Description <input value={description} onChange={(e) => setDescription(e.target.value)} /></label>
        <label className="check"><input type="checkbox" checked={capture} onChange={(e) => setCapture(e.target.checked)} /> Capture immediately (untick to authorize only)</label>
        <div className="row">
          <button disabled={busy} onClick={() => send(1)}>Create payment</button>
          <button disabled={busy} className="secondary" onClick={() => send(2)}>
            Send TWICE with the same Idempotency-Key
          </button>
        </div>
      </div>
      <ErrorBox error={error} />

      {results.length > 0 && (
        <div className="card">
          <h2>Result</h2>
          {results.map((r) => (
            <div key={r.attempt} className="attempt">
              <strong>Attempt {r.attempt}</strong>: HTTP {r.status} ·{" "}
              {r.replayed
                ? <span className="badge captured">replayed: no second charge</span>
                : <span className="badge authorized">executed</span>}
              <div className="muted">
                <Link to={`/payments/${r.payment.id}`}>{r.payment.id}</Link> · {r.payment.status} · {money(r.payment.amount, r.payment.currency)}
              </div>
            </div>
          ))}
          {results.length === 2 && results[0].payment.id === results[1].payment.id && (
            <p className="good">Same payment id both times: idempotency worked. Check the Payments page, there is only one.</p>
          )}
        </div>
      )}
    </>
  );
}
