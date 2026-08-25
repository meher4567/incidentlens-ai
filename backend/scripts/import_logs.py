"""
Import JSONL log file into the database via direct DB or HTTP API.

Usage:
    python -m backend.scripts.import_logs --input logs.jsonl [--api-url http://localhost:8000] [--direct-db]
"""

import argparse
import json
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import httpx
from sqlalchemy import select

from backend.app.db.session import SyncSessionLocal
from backend.app.models.logs import RawLog
from backend.app.models.services import Service


def import_logs_direct(input_path: Path) -> dict:
    """Import JSONL directly into the database (no HTTP API needed)."""
    events = []
    with open(input_path) as f:
        for line in f:
            line = line.strip()
            if line:
                events.append(json.loads(line))

    total = len(events)
    print(f"Loaded {total} events from {input_path}")

    session = SyncSessionLocal()
    try:
        svcs = {r.name: r.id for r in session.execute(select(Service)).scalars().all()}
        counts = {name: 0 for name in svcs}

        batch = []
        for e in events:
            sid = svcs.get(e.get("service", ""))
            if not sid:
                continue
            rl = RawLog(
                service_id=sid,
                timestamp=datetime.fromisoformat(e["timestamp"]),
                ingested_at=datetime.now(timezone.utc),
                level=e.get("level", "INFO"),
                message=e.get("message", ""),
                request_id=uuid.UUID(e["request_id"]) if e.get("request_id") else None,
                trace_id=uuid.UUID(e["trace_id"]) if e.get("trace_id") else None,
                latency_ms=e.get("latency_ms"),
                status_code=e.get("status_code"),
            )
            batch.append(rl)
            counts[e["service"]] = counts.get(e["service"], 0) + 1

            if len(batch) >= 2000:
                session.add_all(batch)
                session.flush()
                batch = []

        if batch:
            session.add_all(batch)
            session.flush()

        session.commit()
        ingested = sum(counts.values())
        print(f"  Service breakdown: {counts}")
        print(f"Done: {ingested}/{total} ingested directly")
        return {"ingested": ingested}
    finally:
        session.close()


def import_logs(input_path: Path, api_url: str, batch_size: int = 1000):
    """Read JSONL file and POST batches to the ingestion API."""
    events = []
    with open(input_path) as f:
        for line in f:
            line = line.strip()
            if line:
                events.append(json.loads(line))

    total = len(events)
    print(f"Loaded {total} events from {input_path}")

    ingested = 0
    errors = []
    start_time = time.time()

    client = httpx.Client(timeout=30.0)
    for i in range(0, total, batch_size):
        batch = events[i : i + batch_size]
        try:
            resp = client.post(
                f"{api_url}/api/logs/batch",
                json={"events": batch},
            )
            resp.raise_for_status()
            data = resp.json()
            ingested += data.get("ingested", 0)
            errors.extend(data.get("errors", []))
        except Exception as exc:
            print(f"Error on batch {i // batch_size}: {exc}")

        if (i + batch_size) % 10000 == 0:
            elapsed = time.time() - start_time
            rate = (i + batch_size) / elapsed if elapsed > 0 else 0
            print(f"  Imported {i + batch_size}/{total} ({rate:.0f} events/sec)")

    elapsed = time.time() - start_time
    rate = total / elapsed if elapsed > 0 else 0
    print(f"Done: {ingested}/{total} ingested in {elapsed:.1f}s ({rate:.0f} events/sec)")
    if errors:
        print(f"  {len(errors)} errors")


def main():
    parser = argparse.ArgumentParser(description="Import JSONL logs into IncidentLens")
    parser.add_argument("--input", type=str, required=True, help="JSONL input file")
    parser.add_argument("--api-url", type=str, default="http://localhost:8000", help="API base URL")
    parser.add_argument("--batch-size", type=int, default=1000, help="Batch size per POST")
    parser.add_argument(
        "--direct-db", action="store_true", help="Import directly into DB (no HTTP)"
    )
    args = parser.parse_args()

    if args.direct_db:
        import_logs_direct(Path(args.input))
    else:
        import_logs(Path(args.input), args.api_url, args.batch_size)


if __name__ == "__main__":
    main()
