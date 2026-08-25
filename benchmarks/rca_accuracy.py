"""
RCA ranker accuracy benchmark: top-1, top-3 accuracy on held-out incidents.

Computes held-out accuracy using ground truth from incident_truth table.

Usage:
    python -m benchmarks.rca_accuracy
"""

import argparse
from datetime import datetime, timezone

import numpy as np
from sqlalchemy import select

from backend.app.db.session import SyncSessionLocal
from backend.app.models.incidents import Incident
from backend.app.services.evaluation import match_incidents_to_truth
from backend.app.services.root_cause import FEATURE_NAMES, load_model, score_incident
from benchmarks.contracts import require
from benchmarks.ingestion_throughput import save_results


def run_benchmark() -> dict:
    run_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    print("RCA accuracy benchmark\n")

    session = SyncSessionLocal()
    try:
        matched = match_incidents_to_truth(session)
        model_data = load_model(session)

        require(model_data is not None, "no RCA model found; run training first")

        if isinstance(model_data, dict):
            model = model_data["model"]
        else:
            model = model_data

        # Evaluate on all matched incidents
        held_out = []
        training = []

        for inc_id, truth in matched.items():
            inc = session.execute(
                select(Incident).where(Incident.id == inc_id)
            ).scalar_one_or_none()
            if inc is None:
                continue
            if truth.split == "held_out":
                held_out.append((inc, truth))
            else:
                training.append((inc, truth))

        def evaluate_set(pairs, label):
            top1 = 0
            top3 = 0
            per_type = {}
            outcomes = []

            for inc, truth in pairs:
                results = score_incident(session, inc, model)

                top1_is_correct = bool(
                    results and results[0]["service_id"] == truth.root_cause_service_id
                )
                if top1_is_correct:
                    top1 += 1
                if any(r["service_id"] == truth.root_cause_service_id for r in results[:3]):
                    top3 += 1
                outcomes.append(1 if top1_is_correct else 0)

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

            return (
                {
                    f"{label}_n": n,
                    f"{label}_top1_accuracy": round(top1 / n, 4) if n > 0 else 0,
                    f"{label}_top3_accuracy": round(top3 / n, 4) if n > 0 else 0,
                    f"{label}_per_type": result_per_type,
                },
                outcomes,
            )

        held_result, held_outcomes = evaluate_set(held_out, "held_out")
        train_result, _training_outcomes = evaluate_set(training, "training")
        require(len(training) >= 3, "at least three matched training incidents are required")
        require(len(held_out) >= 2, "at least two matched held-out incidents are required")

        # Bootstrap 95% CI for held-out
        if len(held_out) > 1:
            rng = np.random.default_rng(42)
            top1_samples = []
            n = len(held_out)
            for _ in range(1000):
                sample_idx = rng.choice(n, size=n, replace=True)
                correct = sum(held_outcomes[int(index)] for index in sample_idx)
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
