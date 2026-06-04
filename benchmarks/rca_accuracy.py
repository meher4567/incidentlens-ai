"""
RCA ranker accuracy benchmark: top-1, top-3 accuracy on held-out incidents.

Computes held-out accuracy using ground truth from incident_truth table.

Usage:
    python -m benchmarks.rca_accuracy
"""
import argparse
import uuid
from datetime import datetime, timedelta, timezone

import numpy as np
from sqlalchemy import select

from backend.app.db.session import SyncSessionLocal
from backend.app.models.incidents import Incident
from backend.app.models.truth import IncidentTruth
from backend.app.services.root_cause import FEATURE_NAMES, load_model, score_incident
from benchmarks.ingestion_throughput import save_results


def match_incidents_to_truth(session) -> dict[uuid.UUID, IncidentTruth]:
    """Match detected incidents to truth by time overlap."""
    truth_rows = session.execute(select(IncidentTruth)).scalars().all()
    incidents = (
        session.execute(select(Incident).where(Incident.closed_at.isnot(None))).scalars().all()
    )

    matched: dict[uuid.UUID, IncidentTruth] = {}
    used_truth: set[uuid.UUID] = set()

    for inc in incidents:
        if inc.start_time is None or inc.end_time is None:
            continue
        best_overlap = timedelta(0)
        best_truth = None
        for t in truth_rows:
            if t.truth_incident_id in used_truth:
                continue
            if t.start_time is None or t.end_time is None:
                continue
            overlap_start = max(inc.start_time, t.start_time)
            overlap_end = min(inc.end_time, t.end_time)
            overlap = overlap_end - overlap_start
            if overlap > best_overlap:
                best_overlap = overlap
                best_truth = t
        if best_truth and best_overlap >= timedelta(seconds=60):
            matched[inc.id] = best_truth
            used_truth.add(best_truth.truth_incident_id)

    return matched


def run_benchmark() -> dict:
    run_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    print("RCA accuracy benchmark\n")

    session = SyncSessionLocal()
    try:
        matched = match_incidents_to_truth(session)
        model_data = load_model()

        if model_data is None:
            print("ERROR: No RCA model found. Run 'python -m backend.scripts.train_rca' first.")
            return {"error": "no_model"}

        if isinstance(model_data, dict):
            model = model_data["model"]
        else:
            model = model_data

        # Evaluate on all matched incidents
        held_out_types = {"db_timeout_cascade", "notification_silent_fail"}
        held_out = []
        training = []

        for inc_id, truth in matched.items():
            inc = session.execute(
                select(Incident).where(Incident.id == inc_id)
            ).scalar_one_or_none()
            if inc is None:
                continue
            if truth.type in held_out_types:
                held_out.append((inc, truth))
            else:
                training.append((inc, truth))

        def evaluate_set(pairs, label):
            top1 = 0
            top3 = 0
            per_type = {}

            for inc, truth in pairs:
                try:
                    results = score_incident(session, inc, model)
                except Exception:
                    continue

                if results and results[0]["service_id"] == truth.root_cause_service_id:
                    top1 += 1
                if any(r["service_id"] == truth.root_cause_service_id for r in results[:3]):
                    top3 += 1

                ttype = truth.type
                if ttype not in per_type:
                    per_type[ttype] = {"correct_top1": 0, "correct_top3": 0, "total": 0}
                per_type[ttype]["total"] += 1
                if results and results[0]["service_id"] == truth.root_cause_service_id:
                    per_type[ttype]["correct_top1"] += 1
                if any(r["service_id"] == truth.root_cause_service_id for r in results[:3]):
                    per_type[ttype]["correct_top3"] += 1

            n = len(pairs)
            result_per_type = {}
            for ttype in per_type:
                pt = per_type[ttype]
                result_per_type[ttype] = {
                    "top1": round(pt["correct_top1"] / pt["total"], 4) if pt["total"] > 0 else 0,
                    "top3": round(pt["correct_top3"] / pt["total"], 4) if pt["total"] > 0 else 0,
                    "total": pt["total"],
                }

            return {
                f"{label}_n": n,
                f"{label}_top1_accuracy": round(top1 / n, 4) if n > 0 else 0,
                f"{label}_top3_accuracy": round(top3 / n, 4) if n > 0 else 0,
                f"{label}_per_type": result_per_type,
            }

        held_result = evaluate_set(held_out, "held_out")
        train_result = evaluate_set(training, "training")

        # Bootstrap 95% CI for held-out
        if len(held_out) > 1:
            rng = np.random.default_rng(42)
            top1_samples = []
            n = len(held_out)
            for _ in range(1000):
                sample_idx = rng.choice(n, size=n, replace=True)
                correct = 0
                for i in sample_idx:
                    inc, truth = held_out[i]
                    try:
                        results = score_incident(session, inc, model)
                        if results and results[0]["service_id"] == truth.root_cause_service_id:
                            correct += 1
                    except Exception:
                        pass
                top1_samples.append(correct / n)
            top1_arr = np.array(top1_samples)
            ci = [
                round(float(np.percentile(top1_arr, 2.5)), 4),
                round(float(np.percentile(top1_arr, 97.5)), 4),
            ]
        else:
            ci = [0, 0]

        # Generalization gap
        gen_gap = round(
            train_result.get("training_top1_accuracy", 1.0)
            - held_result.get("held_out_top1_accuracy", 0),
            4,
        )

        metrics = {
            "benchmark": "rca_accuracy",
            "run_date": run_date,
            "feature_names": FEATURE_NAMES,
            **held_result,
            **train_result,
            "generalization_gap": gen_gap,
            "held_out_top1_ci_95": ci,
        }

        print(f"Held-out top-1: {held_result.get('held_out_top1_accuracy', 0):.2%}")
        print(f"Held-out top-3: {held_result.get('held_out_top3_accuracy', 0):.2%}")
        print(f"Generalization gap: {gen_gap:.2%}")
        print(f"95% CI: [{ci[0]:.2%}, {ci[1]:.2%}]")
        for ttype, vals in held_result.get("held_out_per_type", {}).items():
            print(f"  {ttype}: top1={vals['top1']:.2%}, top3={vals['top3']:.2%}")

        save_results("rca_accuracy", metrics, run_date)

    finally:
        session.close()

    return metrics


def main():
    parser = argparse.ArgumentParser(description="RCA accuracy benchmark")
    parser.parse_args()
    run_benchmark()


if __name__ == "__main__":
    main()
