"""
Seed script: populates services, service_dependencies, and benchmark truth data.

Usage:
    python -m backend.scripts.seed [--truth incidents_truth.jsonl]
"""
import argparse
import json
import sys
import uuid
from pathlib import Path

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.db.session import SyncSessionLocal
from backend.app.models.services import Service, ServiceDependency
from backend.app.models.truth import IncidentTruth


def seed_services(
    session: Session, config_path: str = "generator/config.yaml"
) -> dict[str, uuid.UUID]:
    """
    Seed services from generator config.
    Returns mapping of service_name -> service_id.
    """
    with open(config_path) as f:
        config = yaml.safe_load(f)

    service_map: dict[str, uuid.UUID] = {}
    for svc in config["services"]:
        name = svc["name"]
        existing = session.execute(select(Service).where(Service.name == name)).scalar_one_or_none()

        if existing:
            service_map[name] = existing.id
            print(f"  Service exists: {name} ({existing.id})")
        else:
            svc_obj = Service(name=name)
            session.add(svc_obj)
            session.flush()
            service_map[name] = svc_obj.id
            print(f"  Created service: {name} ({svc_obj.id})")

    session.commit()
    return service_map


def seed_dependencies(
    session: Session,
    service_map: dict[str, uuid.UUID],
    config_path: str = "generator/config.yaml",
) -> int:
    """
    Seed service dependencies from generator config.
    Returns number of dependencies created.
    """
    with open(config_path) as f:
        config = yaml.safe_load(f)

    created = 0
    for dep in config["dependencies"]:
        upstream_name = dep["upstream"]
        downstream_name = dep["downstream"]

        if upstream_name not in service_map or downstream_name not in service_map:
            print(f"  Skipping dependency {upstream_name}->{downstream_name}: service not found")
            continue

        upstream_id = service_map[upstream_name]
        downstream_id = service_map[downstream_name]

        existing = session.execute(
            select(ServiceDependency).where(
                ServiceDependency.upstream_id == upstream_id,
                ServiceDependency.downstream_id == downstream_id,
            )
        ).scalar_one_or_none()

        if existing:
            print(f"  Dependency exists: {upstream_name} -> {downstream_name}")
        else:
            dep_obj = ServiceDependency(
                upstream_id=upstream_id,
                downstream_id=downstream_id,
            )
            session.add(dep_obj)
            created += 1
            print(f"  Created dependency: {upstream_name} -> {downstream_name}")

    session.commit()
    return created


def seed_truth(
    session: Session,
    truth_path: str,
    service_map: dict[str, uuid.UUID],
) -> int:
    """
    Import incident truth data from JSONL file.
    Maps service names to UUIDs.
    Returns number of truth rows imported.
    """
    if not Path(truth_path).exists():
        print(f"  Truth file not found: {truth_path}")
        return 0

    imported = 0
    with open(truth_path) as f:
        for line_idx, line in enumerate(f):
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError as exc:
                print(f"  Skipping line {line_idx}: {exc}")
                continue

            truth_id = uuid.UUID(entry["truth_incident_id"])
            root_cause_name = entry.get("root_cause_service", "")
            root_cause_id = service_map.get(root_cause_name)
            if root_cause_id is None:
                print(f"  Warning: service '{root_cause_name}' not found for truth {truth_id}")
                root_cause_id = uuid.uuid4()  # placeholder

            affected_names = entry.get("affected_services", [])
            affected_ids = []
            for aname in affected_names:
                aid = service_map.get(aname)
                if aid:
                    affected_ids.append(aid)

            generator_run_id = uuid.uuid4()

            existing = session.execute(
                select(IncidentTruth).where(IncidentTruth.truth_incident_id == truth_id)
            ).scalar_one_or_none()

            if existing:
                print(f"  Truth exists: {truth_id}")
                continue

            truth = IncidentTruth(
                truth_incident_id=truth_id,
                type=entry.get("type", ""),
                start_time=entry["start_time"],
                end_time=entry["end_time"],
                root_cause_service_id=root_cause_id,
                affected_service_ids=affected_ids,
                generator_run_id=generator_run_id,
            )
            session.add(truth)
            imported += 1

    session.commit()
    return imported


def main():
    parser = argparse.ArgumentParser(description="Seed IncidentLens database")
    parser.add_argument(
        "--truth", type=str, default="incidents_truth.jsonl", help="Truth incidents file"
    )
    parser.add_argument(
        "--config", type=str, default="generator/config.yaml", help="Generator config path"
    )
    parser.add_argument(
        "--skip-truth",
        action="store_true",
        help="Skip truth import (production-safe, ignores incident_truth)",
    )
    args = parser.parse_args()

    session = SyncSessionLocal()
    try:
        print("=== IncidentLens Seed Script ===\n")

        # Step 1: Seed services
        print("[1/4] Seeding services...")
        service_map = seed_services(session, args.config)
        print(f"  Total services: {len(service_map)}\n")

        # Step 2: Seed dependencies
        print("[2/4] Seeding service dependencies...")
        dep_count = seed_dependencies(session, service_map, args.config)
        print(f"  Total dependencies: {dep_count}\n")

        # Step 3: Seed truth data (optional)
        if args.skip_truth:
            print("[3/4] Skipping truth import (--skip-truth).")
        else:
            print("[3/4] Importing incident truth data...")
            truth_count = seed_truth(session, args.truth, service_map)
            print(f"  Imported {truth_count} truth rows\n")

        # Step 4: Summary
        print("[4/4] Seed complete!")
        print(f"  Services: {len(service_map)}")
        print(f"  Dependencies: {dep_count}")
        if not args.skip_truth:
            from sqlalchemy import func

            total_truth = session.query(func.count(IncidentTruth.truth_incident_id)).scalar()
        else:
            total_truth = "skipped"
        print(f"  Incident truth rows: {total_truth}")

    except Exception as exc:
        session.rollback()
        print(f"\nSeed failed: {exc}", file=sys.stderr)
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main()
