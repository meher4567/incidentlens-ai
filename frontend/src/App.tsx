import React, { Suspense, lazy } from "react";
import { Routes, Route, Link, useLocation } from "react-router-dom";
import Overview from "./pages/Overview";

const ServiceHealth = lazy(() => import("./pages/ServiceHealth"));
const IncidentDetail = lazy(() => import("./pages/IncidentDetail"));
const AnomalyComparison = lazy(() => import("./pages/AnomalyComparison"));

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
          {NAV_ITEMS.map((item) => {
            const isActive =
              item.path === "/" ? location.pathname === "/" : location.pathname.startsWith(item.path);

            return (
              <Link
                key={item.path}
                to={item.path}
                className={`nav-link ${isActive ? "nav-link--active" : ""}`}
              >
                {item.label}
              </Link>
            );
          })}
        </nav>
      </header>
      <main className="app-main">
        <Routes>
          <Route path="/" element={<Overview />} />
          <Route
            path="/services"
            element={
              <Suspense fallback={<div className="loading">Loading service health...</div>}>
                <ServiceHealth />
              </Suspense>
            }
          />
          <Route
            path="/incidents/:incidentId?"
            element={
              <Suspense fallback={<div className="loading">Loading incidents...</div>}>
                <IncidentDetail />
              </Suspense>
            }
          />
          <Route
            path="/anomalies"
            element={
              <Suspense fallback={<div className="loading">Loading anomaly comparison...</div>}>
                <AnomalyComparison />
              </Suspense>
            }
          />
        </Routes>
      </main>
    </div>
  );
}
