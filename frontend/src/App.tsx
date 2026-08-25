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

function NotFound() {
  return (
    <section className="empty-state empty-state--panel">
      <span className="eyebrow">404</span>
      <h2>Page not found</h2>
      <p>The operations view you requested does not exist.</p>
      <Link className="button button--link" to="/">
        Return to overview
      </Link>
    </section>
  );
}

export default function App() {
  const location = useLocation();

  return (
    <div className="app">
      <a className="skip-link" href="#main-content">
        Skip to main content
      </a>
      <header className="app-header">
        <h1 className="app-title">
          <Link to="/">IncidentLens <span>AI</span></Link>
        </h1>
        <nav className="app-nav" aria-label="Primary navigation">
          {NAV_ITEMS.map((item) => {
            const isActive =
              item.path === "/" ? location.pathname === "/" : location.pathname.startsWith(item.path);

            return (
              <Link
                key={item.path}
                to={item.path}
                className={`nav-link ${isActive ? "nav-link--active" : ""}`}
                aria-current={isActive ? "page" : undefined}
              >
                {item.label}
              </Link>
            );
          })}
        </nav>
        <span className="environment-badge">
          <span className="environment-dot" aria-hidden="true" />
          {import.meta.env.VITE_DEMO_MODE === "true" ? "Demo dataset" : "Live pipeline"}
        </span>
      </header>
      <main className="app-main" id="main-content">
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
          <Route path="*" element={<NotFound />} />
        </Routes>
      </main>
    </div>
  );
}
