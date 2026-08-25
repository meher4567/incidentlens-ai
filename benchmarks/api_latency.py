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

from benchmarks.contracts import require
from benchmarks.ingestion_throughput import save_results

ENDPOINTS = [
    ("/healthz", "GET"),
    ("/api/health", "GET"),
    ("/api/services", "GET"),
    ("/api/metrics", "GET"),
    ("/api/incidents", "GET"),
    ("/api/anomalies", "GET"),
]


def run_benchmark(
    api_url: str,
    iterations: int = 50,
    *,
    maximum_p95_ms: float = 250.0,
) -> dict:
    run_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    print(f"API latency benchmark: {len(ENDPOINTS)} endpoints, {iterations} iterations each\n")

    results = {}

    with httpx.Client(timeout=30.0) as client:
        for path, method in ENDPOINTS:
            latencies = []

            # Warm connection pools and route caches without measuring startup.
            client.request(method, f"{api_url}{path}").raise_for_status()
            for _ in range(iterations):
                start = time.perf_counter()
                try:
                    resp = client.get(f"{api_url}{path}")
                    resp.raise_for_status()
                    elapsed = time.perf_counter() - start
                    latencies.append(elapsed)
                except httpx.HTTPError:
                    continue

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
        "maximum_p95_ms": maximum_p95_ms,
        "endpoints": results,
    }

    all_complete = all(endpoint.get("iterations") == iterations for endpoint in results.values())
    all_fast = all(
        "p95_ms" in endpoint and float(endpoint["p95_ms"]) <= maximum_p95_ms
        for endpoint in results.values()
    )
    metrics["status"] = "passed" if all_complete and all_fast else "failed"
    save_results("api_latency", metrics, run_date)
    for path, endpoint in results.items():
        require(
            endpoint.get("iterations") == iterations,
            f"{path} must complete all {iterations} measured requests",
        )
        require(
            float(endpoint["p95_ms"]) <= maximum_p95_ms,
            f"{path} p95 must be at most {maximum_p95_ms:.0f}ms",
        )
    return metrics


def main():
    parser = argparse.ArgumentParser(description="API latency benchmark")
    parser.add_argument("--api-url", type=str, default="http://localhost:8000")
    parser.add_argument("--iterations", type=int, default=50)
    parser.add_argument("--maximum-p95-ms", type=float, default=250.0)
    args = parser.parse_args()
    run_benchmark(
        args.api_url,
        args.iterations,
        maximum_p95_ms=args.maximum_p95_ms,
    )


if __name__ == "__main__":
    main()
