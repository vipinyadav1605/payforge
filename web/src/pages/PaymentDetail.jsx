import { useCallback, useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { api, money, newIdempotencyKey, when } from "../api.js";
import { ErrorBox, StatusBadge } from "../components.jsx";

export default function PaymentDetail() {
  const { id } = useParams();
  const [p, setP] = useState(null);
  const [error, setError] = useState(null);
  const [refundAmount, setRefundAmount] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    api(`/v1/payments/${id}`).then((r) => setP(r.data)).catch(setError);
  }, [id]);
  useEffect(load, [load]);

  async function act(path, body) {
    setBusy(true);
    setError(null);
    try {
      await api(path, { method: "POST", body, idempotencyKey: newIdempotencyKey() });
      load();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }

  if (!p) return <><h1>Payment</h1><ErrorBox error={error} /></>;
  const remaining = p.amount_captured - p.amount_refunded;
  const toMinor = (v) => Math.round(parseFloat(v) * 100);

  return (
    <>
      <h1>{p.id} <StatusBadge status={p.status} /></h1>
      <ErrorBox error={error} />
      <div className="card grid">
        <div><span className="muted">Amount</span><strong>{money(p.amount, p.currency)}</strong></div>
        <div><span className="muted">Captured</span><strong>{money(p.amount_captured, p.currency)}</strong></div>
        <div><span className="muted">Platform fee</span><strong>{money(p.fee_amount, p.currency)}</strong></div>
        <div><span className="muted">Refunded</span><strong>{money(p.amount_refunded, p.currency)}</strong></div>
        <div><span className="muted">Method</span><strong>{p.payment_method}</strong></div>
        <div><span className="muted">Created</span><strong>{when(p.created)}</strong></div>
        {p.failure_code && <div><span className="muted">Failure</span><strong>{p.failure_code}</strong></div>}
        {p.description && <div><span className="muted">Description</span><strong>{p.description}</strong></div>}
      </div>

      <div className="card">
        <h2>Actions</h2>
        <p className="muted">
          Each click sends a fresh Idempotency-Key. Buttons only work when the payment state allows it
          (the API enforces the state machine and returns 409 otherwise).
        </p>
        <div className="row">
          <button disabled={busy || p.status !== "authorized"} onClick={() => act(`/v1/payments/${id}/capture`)}>Capture</button>
          <button disabled={busy || p.status !== "authorized"} onClick={() => act(`/v1/payments/${id}/cancel`)}>Cancel</button>
        </div>
        <div className="row">
          <input
            type="number" step="0.01" min="0.01" placeholder={`Refund amount (max ${(remaining / 100).toFixed(2)})`}
            value={refundAmount} onChange={(e) => setRefundAmount(e.target.value)}
          />
          <button
            disabled={busy || remaining <= 0 || !["captured", "partially_refunded"].includes(p.status)}
            onClick={() => act(`/v1/payments/${id}/refunds`, refundAmount ? { amount: toMinor(refundAmount) } : {})}
          >
            {refundAmount ? "Refund amount" : "Refund remaining"}
          </button>
        </div>
      </div>
    </>
  );
}
