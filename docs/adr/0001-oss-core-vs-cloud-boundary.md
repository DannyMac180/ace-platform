# ADR 0001: OSS/Core Versus Cloud Boundary

- Status: Accepted
- Date: 2026-03-16

## Context

ACE is positioned in this repository as both an open-source product and a hosted service:

- `README.md` describes ACE as "the open-source platform for self-improving AI agents" and also links the managed service at `aceagent.io`, `app.aceagent.io`, and `docs.aceagent.io`.
- `README.md` and `docs/SELF_HOSTED_DEPLOYMENT.md` document self-hosting for the API, MCP server, workers, scheduler, PostgreSQL, Redis, and the web app.
- `docs/ARCHITECTURE.md` and `docs/IMPLEMENTATION_PLAN.md` describe a codebase split where `ace_core/` is the upstream ACE framework and `ace_platform/` is the hosted platform layer that wraps it.
- `docs/IMPLEMENTATION_PLAN.md` and `docs/IMPLENTATION_PLAN_CRITIQUES.md` also call out the need to separate the self-hosted/open-source posture from the managed SaaS posture, including optional billing and platform-managed keys.

That combination means ACE needs an explicit boundary so contributors, operators, and future ADRs all use the same rule for what belongs in the public repository and what stays in private cloud operations.

## Decision

All reusable product code and product-facing documentation that define how ACE works are public and live in this repository. Private cloud concerns are limited to the hosted runtime, operator credentials, tenant data, and internal operational systems needed to run the managed service safely.

### Public OSS/Core Surface

The following are public and should remain versioned in this repository:

- `ace_core/`: the upstream ACE framework, prompts, finance examples, and related adaptation logic.
- `ace_platform/`: the API, MCP server, worker code, data models, auth flows, metering hooks, and other backend application code.
- `web/`: the dashboard frontend code.
- `docs-site/`, `docs/`, `README.md`, and self-hosting guides: product behavior, architecture, deployment guidance, and operational documentation that self-hosters need.
- `playbooks/`, tests, and public infrastructure manifests such as `docker-compose.yml`, `Dockerfile`, and Fly configuration templates.

In short: if a capability must be inspectable, forkable, testable, or runnable by a self-hosting user, it belongs in the public repository.

### Private Cloud Surface

The following stay private to ACE's managed cloud operation and do not belong in the public repository as live assets:

- Production secrets and credentials, including provider keys, JWT/session secrets, OAuth client secrets, webhook secrets, and infrastructure access tokens.
- Managed service infrastructure state and operator-only configuration for the live `aceagent.io`, `app.aceagent.io`, and `docs.aceagent.io` environments.
- Tenant data from the hosted product, including user accounts, playbooks, outcomes, usage records, billing records, and audit trails.
- Internal-only operational systems and procedures such as production dashboards, alert routing, incident handling, support tooling, and admin-only runbooks that would create unnecessary security or abuse risk if fully exposed as live systems.
- Third-party service accounts used to operate the hosted product, such as Stripe, Resend, Sentry, OAuth applications, and managed database/Redis instances.

In short: if the asset is environment-specific, security-sensitive, customer-specific, or only required to operate the hosted service, it stays private.

## Rationale

This boundary keeps ACE portable without pretending that a managed cloud service has no private layer.

1. It preserves the repository as the full public product contract. Self-hosters can inspect the code, run the documented stack, and understand the architecture without depending on hidden application logic.
2. It keeps the hosted service secure. Secrets, customer data, and operator systems are not source artifacts and should not be treated as open-source deliverables.
3. It avoids a false split where `ace_core/` is public but `ace_platform/` is private. The current repository structure and self-hosting docs show that both layers are part of the public product; the cloud boundary sits at runtime operations, not at the package boundary.
4. It supports both delivery modes described in the docs: self-hosted deployments and a managed SaaS offering. Public code stays shared, while private operations can evolve independently per environment.

## Consequences

- New features should default to public implementation when they change ACE product behavior, APIs, schemas, UI flows, or deployment guidance.
- Hosted-only additions should be implemented as configuration, credentials, operational automation, or service accounts outside the repository unless they are needed for self-hosting users too.
- When a feature depends on a managed provider such as Stripe or a platform-managed model key, the repository should expose the integration points and feature flags, while the live account configuration remains private.
- Future docs should describe private services in terms of responsibilities and boundaries, not by publishing live secrets, customer data, or operator-only access details.

## Rejected Alternative

Treat `ace_core/` as the only public layer and keep `ace_platform/` plus the web app private.

This was rejected because it conflicts with the current repository contents and documentation. The repo already publishes the platform backend, dashboard, tests, architecture docs, and self-hosted deployment instructions. Making the package split the OSS/cloud boundary would create a misleading architecture story and weaken the self-hosting contract.
