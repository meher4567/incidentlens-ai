"""
Ingestion throughput benchmark.
Measures sustained logs/sec on batch ingestion.

Usage:
    python -m benchmarks.ingestion_throughput --events 100000 --batch-size 1000
"""
import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
import numpy as np

BASE_DIR = Path(__file__).resolve().parent
RESULTS_DIR = BASE_DIR / "results"


def save_results(benchmark_name: str, metrics: dict, run_date: str) -> None:
    """Save benchmark results as JSON and markdown."""
    dated_dir = RESULTS_DIR / run_date
    dated_dir.mkdir(parents=True, exist_ok=True)

    # JSON
    json_path = dated_dir / f"{benchmark_name}.json"
    with open(json_path, "w") as f:
        json.dump(metrics, f, indent=2, default=str)

    # Markdown
    md_path = dated_dir / f"{benchmark_name}.md"
    with open(md_path, "w") as f:
        f.write(f"# {benchmark_name}\n\n")
        f.write(f"Date: {run_date}\n\n")
        f.write("| Metric | Value |\n")
        f.write("| ------ | ----- |\n")
        for k, v in metrics.items():
            f.write(f"| {k} | {v} |\n")

    print(f"Results saved to {dated_dir}/")


def run_benchmark(api_url: str, total_events: int, batch_size: int):
    run_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    print(f"Ingestion throughput benchmark: {total_events} events, batch size {batch_size}")

    # Generate test log events
    events = []
    for i in range(total_events):
        events.append(
            {
                "timestamp": "2026-01-01T00:00:00.000Z",
                "service": "api-gateway",
                "level": "INFO",
                "message": f"Benchmark test log event {i}",
                "latency_ms": 100,
                "status_code": 200,
            }
        )

    ingested = 0
    errors = 0
    latencies = []
    start = time.time()

    client = httpx.Client(timeout=60.0)
    for i in range(0, total_events, batch_size):
        batch = events[i : i + batch_size]
        batch_start = time.time()
        try:
            resp = client.post(
                f"{api_url}/api/logs/batch",
                json={"events": batch},
            )
            batch_latency = time.time() - batch_start
            latencies.append(batch_latency)
            if resp.status_code == 201:
                data = resp.json()
                ingested += data.get("ingested", 0)
            else:
                errors += len(batch)
        except Exception:
            errors += len(batch)

    elapsed = time.time() - start
    rate = total_events / elapsed if elapsed > 0 else 0

    lat_arr = np.array(latencies) if latencies else np.zeros(1)
    metrics = {
        "benchmark": "ingestion_throughput",
        "total_events": total_events,
        "batch_size": batch_size,
        "ingested": ingested,
        "errors": errors,
        "elapsed_seconds": round(elapsed, 2),
        "throughput_logs_per_sec": round(rate, 1),
        "p50_batch_latency_ms": round(float(np.percentile(lat_arr, 50)) * 1000, 1),
        "p95_batch_latency_ms": round(float(np.percentile(lat_arr, 95)) * 1000, 1),
    }

    print("\nResults:")
    for k, v in metrics.items():
        print(f"  {k}: {v}")

    save_results("ingestion_throughput", metrics, run_date)
    return metrics


def main():
    parser = argparse.ArgumentParser(description="Ingestion throughput benchmark")
    parser.add_argument("--events", type=int, default=100000)
    parser.add_argument("--batch-size", type=int, default=1000)
    parser.add_argument("--api-url", type=str, default="http://localhost:8000")
    args = parser.parse_args()
    run_benchmark(args.api_url, args.events, args.batch_size)


if __name__ == "__main__":
    main()
