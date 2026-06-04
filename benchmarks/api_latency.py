"""
API latency benchmark: p50/p95 of dashboard endpoints.

Measures response times for key dashboard API endpoints.

Usage:
    python -m benchmarks.api_latency
"""
import argparse
import time
from datetime import datetime, timezone

import httpx
import numpy as np

from benchmarks.ingestion_throughput import save_results

ENDPOINTS = [
    ("/healthz", "GET"),
    ("/api/health", "GET"),
    ("/api/services", "GET"),
    ("/api/metrics", "GET"),
    ("/api/incidents", "GET"),
    ("/api/anomalies", "GET"),
]


def run_benchmark(api_url: str, iterations: int = 50) -> dict:
    run_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    print(f"API latency benchmark: {len(ENDPOINTS)} endpoints, {iterations} iterations each\n")

    client = httpx.Client(timeout=30.0)
    results = {}

    for path, method in ENDPOINTS:
        latencies = []

        for i in range(iterations):
            start = time.time()
            try:
                if method == "GET":
                    resp = client.get(f"{api_url}{path}")
                resp.raise_for_status()
                elapsed = time.time() - start
                latencies.append(elapsed)
            except Exception:
                pass

        if latencies:
            arr = np.array(latencies) * 1000  # Convert to ms
            results[path] = {
                "method": method,
                "iterations": len(latencies),
                "p50_ms": round(float(np.percentile(arr, 50)), 2),
                "p95_ms": round(float(np.percentile(arr, 95)), 2),
                "p99_ms": round(float(np.percentile(arr, 99)), 2),
                "mean_ms": round(float(arr.mean()), 2),
                "min_ms": round(float(arr.min()), 2),
                "max_ms": round(float(arr.max()), 2),
            }
            print(
                f"  {method} {path}: p50={results[path]['p50_ms']}ms, p95={results[path]['p95_ms']}ms"
            )
        else:
            results[path] = {"method": method, "error": "no successful requests"}
            print(f"  {method} {path}: no successful requests")

    metrics = {
        "benchmark": "api_latency",
        "run_date": run_date,
        "api_url": api_url,
        "iterations": iterations,
        "endpoints": results,
    }

    save_results("api_latency", metrics, run_date)
    return metrics


def main():
    parser = argparse.ArgumentParser(description="API latency benchmark")
    parser.add_argument("--api-url", type=str, default="http://localhost:8000")
    parser.add_argument("--iterations", type=int, default=50)
    args = parser.parse_args()
    run_benchmark(args.api_url, args.iterations)


if __name__ == "__main__":
    main()
