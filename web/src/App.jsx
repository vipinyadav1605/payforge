import { Link, NavLink, Navigate, Route, Routes, useNavigate } from "react-router-dom";
import { clearKey, getKey } from "./api.js";
import Login from "./pages/Login.jsx";
import Overview from "./pages/Overview.jsx";
import Payments from "./pages/Payments.jsx";
import PaymentDetail from "./pages/PaymentDetail.jsx";
import NewPayment from "./pages/NewPayment.jsx";
import Webhooks from "./pages/Webhooks.jsx";

function Protected({ children }) {
  return getKey() ? children : <Navigate to="/login" replace />;
}

function Shell({ children }) {
  const navigate = useNavigate();
  return (
    <div className="shell">
      <aside>
        <Link to="/" className="brand">PayForge</Link>
        <nav>
          <NavLink to="/" end>Overview</NavLink>
          <NavLink to="/payments">Payments</NavLink>
          <NavLink to="/new">New test payment</NavLink>
          <NavLink to="/webhooks">Webhooks</NavLink>
        </nav>
        <button className="link" onClick={() => { clearKey(); navigate("/login"); }}>
          Sign out
        </button>
      </aside>
      <main>{children}</main>
    </div>
  );
}

export default function App() {
  const page = (el) => <Protected><Shell>{el}</Shell></Protected>;
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/" element={page(<Overview />)} />
      <Route path="/payments" element={page(<Payments />)} />
      <Route path="/payments/:id" element={page(<PaymentDetail />)} />
      <Route path="/new" element={page(<NewPayment />)} />
      <Route path="/webhooks" element={page(<Webhooks />)} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
