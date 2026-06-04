import React from "react";
import { Routes, Route, Link, useLocation } from "react-router-dom";
import Overview from "./pages/Overview";
import ServiceHealth from "./pages/ServiceHealth";
import IncidentDetail from "./pages/IncidentDetail";
import AnomalyComparison from "./pages/AnomalyComparison";

const NAV_ITEMS = [
  { path: "/", label: "Overview" },
  { path: "/services", label: "Service Health" },
  { path: "/incidents", label: "Incidents" },
  { path: "/anomalies", label: "Anomaly Methods" },
];

export default function App() {
  const location = useLocation();

  return (
    <div className="app">
      <header className="app-header">
        <h1 className="app-title">IncidentLens AI</h1>
        <nav className="app-nav">
          {NAV_ITEMS.map((item) => (
            <Link
              key={item.path}
              to={item.path}
              className={`nav-link ${location.pathname === item.path ? "nav-link--active" : ""}`}
            >
              {item.label}
            </Link>
          ))}
        </nav>
      </header>
      <main className="app-main">
        <Routes>
          <Route path="/" element={<Overview />} />
          <Route path="/services" element={<ServiceHealth />} />
          <Route path="/incidents/:incidentId?" element={<IncidentDetail />} />
          <Route path="/anomalies" element={<AnomalyComparison />} />
        </Routes>
      </main>
    </div>
  );
}