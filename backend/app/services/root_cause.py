"""
Root Cause Analysis (RCA) ranker.

Trains an interpretable logistic regression model on 60 training incidents
(3 types × 20 each), then scores services in held-out incidents.

Features (per service per incident):
1. is_earliest — first alert in incident
2. earliest_seconds_gap — gap to second alert
3. upstream_position — downstream count in incident
4. blast_radius — downstream count in full dep graph
5. metric_jump_magnitude — max |z-score| across alerts
6. alert_count — total alerts in incident

Model: LogisticRegression with class_weight='balanced'
Persists score, rank, feature_vector, and feature_contributions.
"""
import pickle
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, TypedDict

import networkx as nx
import numpy as np
from sklearn.linear_model import LogisticRegression
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.models.alerts import Alert, DeduplicatedAlert
from backend.app.models.anomalies import Anomaly, AnomalyDetector
from backend.app.models.incidents import Incident, IncidentAlert, IncidentRootCauseScore
from backend.app.models.services import ServiceDependency

settings = get_settings()

MODEL_PATH = Path(settings.models_dir) / "rca_ranker.pkl"
FEATURE_NAMES = [
    "is_earliest",
    "earliest_seconds_gap",
    "upstream_position",
    "blast_radius",
    "metric_jump_magnitude",
    "alert_count",
]


class RootCauseScoreResult(TypedDict):
    service_id: uuid.UUID
    score: float
    rank: int
    feature_vector: dict[str, float]
    feature_contributions: dict[str, float]


def _build_dep_graph(session: Session) -> nx.DiGraph:
    G = nx.DiGraph()
    deps = session.execute(select(ServiceDependency)).scalars().all()
    for dep in deps:
        G.add_edge(dep.upstream_id, dep.downstream_id)
    return G


def _get_downstream_services(G: nx.DiGraph, service_id: uuid.UUID) -> set[uuid.UUID]:
    """Get all downstream services reachable from service_id."""
    downstream: set[uuid.UUID] = set()
    if service_id not in G:
        return downstream
    try:
        descendants = nx.descendants(G, service_id)
        downstream.update(descendants)
    except nx.NetworkXError:
        pass
    return downstream


def _get_canonical_alerts_for_incident(
    session: Session,
    incident_id: uuid.UUID,
) -> list[Alert]:
    """Get canonical (non-duplicate) alerts attached to an incident."""
    alert_links = (
        session.execute(select(IncidentAlert).where(IncidentAlert.incident_id == incident_id))
        .scalars()
        .all()
    )
    if not alert_links:
        return []

    alert_ids = [a.alert_id for a in alert_links]
    dup_ids = session.execute(select(DeduplicatedAlert.duplicate_alert_id)).scalars().all()
    dup_set = set(dup_ids)

    alerts = session.execute(select(Alert).where(Alert.id.in_(alert_ids))).scalars().all()

    # Return only canonical alerts
    return [a for a in alerts if a.id not in dup_set]


def extract_features(
    session: Session,
    incident: Incident,
    service_id: uuid.UUID,
    G: nx.DiGraph,
) -> dict[str, float]:
    """
    Extract 6 features for a service in an incident.
    """
    features: dict[str, float] = {}

    # Get all alerts in incident
    all_alerts = _get_canonical_alerts_for_incident(session, incident.id)
    if not all_alerts:
        return {name: 0.0 for name in FEATURE_NAMES}

    # Service-specific alerts
    service_alerts = [a for a in all_alerts if a.service_id == service_id]
    if not service_alerts:
        return {name: 0.0 for name in FEATURE_NAMES}

    # Sort by earliest start
    all_alerts.sort(key=lambda a: a.start_window)
    service_alerts.sort(key=lambda a: a.start_window)

    # 1. is_earliest — is this service's first alert THE first alert in incident?
    first_alert_service = all_alerts[0].service_id
    features["is_earliest"] = 1.0 if first_alert_service == service_id else 0.0

    # 2. earliest_seconds_gap — gap to second service's first alert
    if first_alert_service == service_id:
        # Find second distinct service's first alert
        second_alerts = [a for a in all_alerts if a.service_id != service_id]
        if second_alerts:
            gap = (second_alerts[0].start_window - service_alerts[0].start_window).total_seconds()
            features["earliest_seconds_gap"] = max(0.0, float(gap))
        else:
            features["earliest_seconds_gap"] = 0.0
    else:
        features["earliest_seconds_gap"] = 0.0

    # 3. upstream_position — count of services in incident that are downstream of this service
    downstream = _get_downstream_services(G, service_id)
    incident_services = set(incident.affected_services)
    features["upstream_position"] = float(len(downstream & incident_services))

    # 4. blast_radius — count of all services downstream in full dep graph
    features["blast_radius"] = float(len(downstream))

    # 5. metric_jump_magnitude — max |z-score| for this service's anomalies
    max_z = 0.0
    for alert in service_alerts:
        for anomaly_id in alert.anomaly_ids:
            anomaly = session.execute(
                select(Anomaly).where(Anomaly.id == anomaly_id)
            ).scalar_one_or_none()
            if anomaly and anomaly.detector == AnomalyDetector.MAD:
                max_z = max(max_z, abs(float(anomaly.score)))
    features["metric_jump_magnitude"] = max_z

    # 6. alert_count — number of canonical alerts for this service
    features["alert_count"] = float(len(service_alerts))

    return features


def train_ranker(
    session: Session,
    training_incidents: list[Incident],
    truth_data: dict[uuid.UUID, uuid.UUID],  # incident_id -> true_root_cause_service_id
) -> LogisticRegression:
    """
    Train logistic regression RCA ranker on training incidents.
    Returns fitted model.
    """
    G = _build_dep_graph(session)
    X: list[list[float]] = []
    y: list[int] = []

    for inc in training_incidents:
        true_root = truth_data.get(inc.id)
        if true_root is None:
            continue

        for service_id in inc.affected_services:
            features = extract_features(session, inc, service_id, G)
            feature_vector = [features[name] for name in FEATURE_NAMES]
            X.append(feature_vector)
            y.append(1 if service_id == true_root else 0)

    if len(X) < 10 or sum(y) < 3:
        # Not enough data: return untrained model
        return LogisticRegression(class_weight="balanced", solver="lbfgs")

    X_arr = np.array(X)
    y_arr = np.array(y)

    model = LogisticRegression(
        class_weight="balanced",
        solver="lbfgs",
        max_iter=1000,
    )
    model.fit(X_arr, y_arr)

    # Save model with metadata
    MODEL_PATH.parent.mkdir(exist_ok=True)
    with open(MODEL_PATH, "wb") as f:
        pickle.dump(
            {
                "model": model,
                "feature_names": FEATURE_NAMES,
                "trained_at": datetime.now(timezone.utc).isoformat(),
                "n_training_incidents": len(training_incidents),
            },
            f,
        )

    return model


def load_model() -> Optional[LogisticRegression | dict]:
    """
    Load trained RCA ranker model.
    Handles both raw model and dict-with-metadata formats.
    """
    if not MODEL_PATH.exists():
        return None
    with open(MODEL_PATH, "rb") as f:
        data = pickle.load(f)
    if isinstance(data, dict):
        return data
    return data


def score_incident(
    session: Session,
    incident: Incident,
    model: LogisticRegression,
) -> list[RootCauseScoreResult]:
    """
    Score all affected services in an incident using the trained RCA ranker.
    Returns list of dicts with score, rank, feature_vector, feature_contributions.
    """
    G = _build_dep_graph(session)
    results: list[RootCauseScoreResult] = []

    for service_id in incident.affected_services:
        features = extract_features(session, incident, service_id, G)
        feature_vector = [features[name] for name in FEATURE_NAMES]

        # Predict probability
        try:
            proba = model.predict_proba([feature_vector])[0]
            score = float(proba[1]) if len(proba) > 1 else float(proba[0])
        except Exception:
            score = 0.0

        # Feature contributions = coefficient * feature_value
        contributions: dict[str, float] = {}
        if hasattr(model, "coef_"):
            for i, name in enumerate(FEATURE_NAMES):
                contributions[name] = round(float(model.coef_[0][i]) * feature_vector[i], 6)

        results.append(
            {
                "service_id": service_id,
                "score": score,
                "rank": 0,
                "feature_vector": dict(zip(FEATURE_NAMES, feature_vector)),
                "feature_contributions": contributions,
            }
        )

    # Sort by score descending
    results.sort(key=lambda x: x["score"], reverse=True)

    # Assign ranks
    for i, r in enumerate(results):
        r["rank"] = i + 1

    return results


def run_rca_on_closed_incidents(session: Session) -> int:
    """
    Run RCA ranking on all closed-but-not-scored incidents.
    Returns number of incidents scored.
    """
    model_data = load_model()
    if model_data is None:
        return 0

    # Handle both raw model and dict-with-metadata formats
    if isinstance(model_data, dict):
        maybe_model = model_data.get("model")
        if not isinstance(maybe_model, LogisticRegression):
            return 0
        model = maybe_model
    else:
        model = model_data

    # Find closed incidents that haven't been scored
    scored_ids = (
        session.execute(select(IncidentRootCauseScore.incident_id).distinct()).scalars().all()
    )
    scored_set: set[uuid.UUID] = set(scored_ids)

    closed_stmt = select(Incident).where(Incident.closed_at.isnot(None))
    if scored_set:
        closed_stmt = closed_stmt.where(~Incident.id.in_(scored_set))
    closed_incidents = session.execute(closed_stmt).scalars().all()

    scored_count = 0
    for inc in closed_incidents:
        results = score_incident(session, inc, model)
        for r in results:
            rc_score = IncidentRootCauseScore(
                incident_id=inc.id,
                service_id=r["service_id"],
                score=r["score"],
                rank=r["rank"],
                feature_vector=r["feature_vector"],
                feature_contributions=r["feature_contributions"],
            )
            session.add(rc_score)
        scored_count += 1

    session.commit()
    return scored_count
