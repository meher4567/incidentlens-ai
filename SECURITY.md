# Security Policy

## Supported version

Security fixes are applied to the latest commit on the default branch. This is
a portfolio/reference system, not a hosted service with a long-term support
matrix.

## Reporting a vulnerability

Do not open a public issue for a suspected vulnerability. Use GitHub's private
vulnerability reporting for this repository. Include the affected component,
reproduction steps, impact, and any suggested mitigation. Avoid including real
credentials or sensitive telemetry.

You should receive acknowledgement within seven days. Valid reports will be
triaged, fixed on a private branch, and disclosed after a patched version is
available.

## Current security boundary

- Production Compose requires an API key for mutating API routes.
- PostgreSQL, Redis, the API, and Prometheus metrics stay on the private Compose
  network behind Nginx.
- Requests have a body limit, ingestion quota, request IDs, security headers,
  and constant-time API-key comparison.
- Backend containers run non-root with a read-only filesystem,
  `no-new-privileges`, dropped capabilities, and PID limits.
- Runtime Python and JavaScript dependencies are audited in CI; CodeQL analyzes
  Python and JavaScript/TypeScript.
- Secrets are runtime inputs. They must not be committed, logged, embedded in
  frontend build arguments, or added to example data.

## Deployment responsibilities

The included stack is production-shaped, not a complete internet-facing
security platform. Operators must add TLS, a secret manager, authenticated read
access/RBAC, ingress-level fail-closed quotas, network policy, centralized audit
logs, vulnerability scanning for built images, managed backups, monitoring, and
an incident-response process appropriate to their environment.

Synthetic repository data must never be replaced with real customer logs in a
public fork. Treat database backups and trained model artifacts as sensitive.
