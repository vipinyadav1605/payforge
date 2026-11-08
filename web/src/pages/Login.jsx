import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, setKey } from "../api.js";

export default function Login() {
  const navigate = useNavigate();
  const [apiKey, setApiKey] = useState("");
  const [adminToken, setAdminToken] = useState("dev-admin-token-change-me");
  const [name, setName] = useState("Demo Store");
  const [error, setError] = useState("");

  async function signIn(e) {
    e.preventDefault();
    setError("");
    try {
      await api("/v1/me", { key: apiKey.trim() });
      setKey(apiKey.trim());
      navigate("/");
    } catch (err) {
      setError(err.message);
    }
  }

  async function createDemo() {
    setError("");
    try {
      const { data } = await api("/admin/merchants", {
        method: "POST",
        adminToken,
        key: "",
        body: { name, email: `${name.replace(/\s+/g, "").toLowerCase()}@example.com` },
      });
      setKey(data.api_key);
      navigate("/");
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <div className="login">
      <h1>PayForge</h1>
      <p className="muted">Merchant dashboard (development build)</p>

      <form className="card" onSubmit={signIn}>
        <h2>Sign in with an API key</h2>
        <input placeholder="pf_test_..." value={apiKey} onChange={(e) => setApiKey(e.target.value)} />
        <button disabled={!apiKey.trim()}>Sign in</button>
      </form>

      <div className="card">
        <h2>Or create a demo merchant</h2>
        <p className="muted">
          Uses the admin token from your <code>.env</code>. Development only: a real product would
          never expose admin operations in the merchant UI.
        </p>
        <input placeholder="Store name" value={name} onChange={(e) => setName(e.target.value)} />
        <input placeholder="Admin token" value={adminToken} onChange={(e) => setAdminToken(e.target.value)} />
        <button onClick={createDemo}>Create merchant and sign in</button>
      </div>
      {error && <p className="error">{error}</p>}
    </div>
  );
}
