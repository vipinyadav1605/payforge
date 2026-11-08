import { useCallback, useEffect, useState } from "react";
import { api } from "../api.js";
import { ErrorBox } from "../components.jsx";

export default function Webhooks() {
  const [endpoints, setEndpoints] = useState([]);
  const [deliveries, setDeliveries] = useState([]);
  const [url, setUrl] = useState("http://host.docker.internal:9000/hook");
  const [created, setCreated] = useState(null);
  const [error, setError] = useState(null);

  const load = useCallback(async () => {
    try {
      const [e, d] = await Promise.all([api("/v1/webhook-endpoints"), api("/v1/webhook-deliveries?limit=20")]);
      setEndpoints(e.data);
      setDeliveries(d.data.data);
    } catch (err) {
      setError(err);
    }
  }, []);

  useEffect(() => {
    load();
    const t = setInterval(load, 4000); // poll so you can watch retries happen
    return () => clearInterval(t);
  }, [load]);

  async function add(e) {
    e.preventDefault();
    setError(null);
    try {
      const { data } = await api("/v1/webhook-endpoints", { method: "POST", body: { url } });
      setCreated(data);
      load();
    } catch (err) {
      setError(err);
    }
  }

  async function remove(id) {
    await api(`/v1/webhook-endpoints/${id}`, { method: "DELETE" }).catch(setError);
    load();
  }

  async function replay(id) {
    await api(`/v1/webhook-deliveries/${id}/replay`, { method: "POST" }).catch(setError);
    load();
  }

  return (
    <>
      <h1>Webhooks</h1>
      <ErrorBox error={error} />

      <form className="card row" onSubmit={add}>
        <input style={{ flex: 1 }} value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://your-server/hook" />
        <button>Add endpoint</button>
      </form>
      {created && (
        <div className="card">
          <strong>Signing secret (shown once, copy it now):</strong>
          <pre>{created.secret}</pre>
          <p className="muted">Use it with <code>python scripts/webhook_receiver.py &lt;secret&gt;</code> to verify signatures.</p>
        </div>
      )}

      <h2>Endpoints</h2>
      <table>
        <thead><tr><th>ID</th><th>URL</th><th>Events</th><th></th></tr></thead>
        <tbody>
          {endpoints.map((e) => (
            <tr key={e.id}>
              <td>{e.id}</td><td>{e.url}</td><td>{e.events.join(", ")}</td>
              <td><button className="link" onClick={() => remove(e.id)}>Remove</button></td>
            </tr>
          ))}
          {endpoints.length === 0 && <tr><td colSpan="4" className="muted">No endpoints yet.</td></tr>}
        </tbody>
      </table>

      <h2>Deliveries <small className="muted">(auto-refreshing)</small></h2>
      <table>
        <thead><tr><th>Delivery</th><th>Event</th><th>Status</th><th>Attempts</th><th>Last result</th><th></th></tr></thead>
        <tbody>
          {deliveries.map((d) => (
            <tr key={d.id}>
              <td>{d.id}</td>
              <td>{d.event_id}</td>
              <td><span className={`badge ${d.status}`}>{d.status}</span></td>
              <td>{d.attempts}</td>
              <td>{d.last_error || (d.last_status_code ? `HTTP ${d.last_status_code}` : "-")}</td>
              <td>{["dead", "retrying"].includes(d.status) && <button className="link" onClick={() => replay(d.id)}>Replay</button>}</td>
            </tr>
          ))}
          {deliveries.length === 0 && <tr><td colSpan="6" className="muted">Nothing delivered yet.</td></tr>}
        </tbody>
      </table>
    </>
  );
}
