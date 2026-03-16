# ACE Platform Next Iteration — Product Spec and Developer Task Breakdown

**Prepared for:** Dan McAteer  
**Document type:** Product spec / implementation blueprint  
**Status:** Working draft for execution  
**Date:** March 15, 2026

---

## Executive Summary

ACE should evolve into a **local-first, open-source playbook engine** with a **hosted cloud product for convenience, collaboration, and governance**.

The central product decision is to separate:

- **Local capability** from **hosted convenience**
- **Individual hosted value** from **team collaboration value**
- **Open-source engine** from **private cloud services**

This preserves the benefits of open-source distribution and local adoption while protecting a durable revenue layer for hosted customers.

The recommended packaging model is:

| Offer | Core value |
|---|---|
| **ACE OSS** | Fully usable local, self-managed single-user runtime |
| **ACE Cloud Personal** | Hosted convenience for one user |
| **ACE Cloud Team** | Hosted collaboration for multi-user teams |
| **ACE Enterprise** | Governance, compliance, and private deployment options |

The core architectural rule is:

> **Premium value must depend on private services you operate, not just hidden UI or local license checks.**

This spec organizes the next iteration of ACE around five outcomes:

1. Establish a clean open-source/core versus private-cloud boundary.
2. Preserve and strengthen the hosted individual plan.
3. Add team-oriented cloud features without complicating the single-user experience.
4. Improve activation with self-setup and benchmark-driven onboarding.
5. Create a work breakdown that can be handed to an AI coding agent or converted into engineering tickets.

---

## Table of Contents

1. Product Vision and Goals
2. Strategic Decisions
3. Product Packaging and Segmentation
4. User Segments and Jobs to Be Done
5. Scope and Non-Goals
6. Functional Requirements
7. Technical Architecture
8. Data Model and Entitlements
9. Developer Task Breakdown
10. Recommended Release Plan
11. Success Metrics
12. Risks and Open Questions
13. Appendix: Suggested Package and Service Layout

---

## 1. Product Vision and Goals

### Vision

ACE becomes the standard **context engineering and playbook learning layer** for developers and AI agents:

- **Local-first** for trust, control, and easy experimentation
- **Hosted** for convenience, sync, backups, managed inference, and team workflows
- **Extensible** enough to support CLI, IDE, MCP, and agent-native usage

### Product Goal

Enable a user or team to:

- capture successful trajectories and operating knowledge
- refine that knowledge into reusable playbooks
- apply those playbooks inside agent workflows
- continuously improve results over time

### Business Goal

Increase paying customers by improving three parts of the funnel:

- **Awareness:** open-source distribution and local adoption
- **Activation:** self-setup, better onboarding, faster time-to-value
- **Conversion and expansion:** hosted personal plans for convenience; hosted team plans for collaboration; enterprise for governance

### Guiding Principles

1. **The OSS version must be genuinely useful.** It cannot feel like a crippled demo.
2. **Hosted individual users remain first-class customers.** Convenience is a valid product, not just collaboration.
3. **Team value should feel additive.** Team features should build on top of the personal hosted experience.
4. **The security boundary is the server boundary.** Premium features are enforced in cloud services.
5. **One core runtime, multiple deployment modes.** Avoid separate products that drift apart.

---

## 2. Strategic Decisions

### Decision 1 — Separate deployment from collaboration

Do not model the business as `free vs paid` or `individual vs team` only.

Instead, separate:

- **deployment mode**: local OSS, ACE Cloud, enterprise self-hosted
- **workspace plan**: personal, team, enterprise
- **usage envelope**: storage, eval runs, managed inference, seats

This allows ACE Cloud Personal to remain strong and clear:

- a single user can still pay for hosted convenience
- teams pay more for shared workflows and administration
- enterprise pays for governance and deployment control

### Decision 2 — Personal hosted users should live inside the same workspace model

Every customer should belong to a workspace.

A personal hosted workspace is simply:

- `plan = personal`
- `seat_limit = 1`
- `deployment_mode = cloud`

This avoids a separate product branch for individuals.

### Decision 3 — Open-source the engine, not the cloud control plane

Open-source should include the local engine and local runtime:

- playbook engine
- local API and CLI
- local MCP server
- local storage
- provider adapters
- import/export formats

Private hosted code should include the control plane and managed services:

- auth and sessions
- subscriptions and billing
- entitlements and plan checks
- cloud sync
- hosted eval workers
- usage metering
- managed inference gateway
- org administration and audit systems

### Decision 4 — Improve onboarding with an AI-friendly self-setup path

A major activation goal is to let an AI coding agent set ACE up for a user or for itself.

The desired end state is a simple onboarding flow such as:

- `ace init`
- `ace doctor`
- `ace benchmark`
- `ace seed`

This should produce first-run value without requiring the user to manually wire every component.

### Decision 5 — Treat Codex/OpenAI OAuth as a hosted convenience layer, not the moat

Codex or OpenAI OAuth can reduce friction, but the product moat remains ACE itself:

- playbook memory
- refinement loop
- sync and continuity
- collaboration and governance
- hosted convenience and metrics

---

## 3. Product Packaging and Segmentation

### 3.1 Packaging Overview

| Capability | ACE OSS | Cloud Personal | Cloud Team | Enterprise |
|---|---:|---:|---:|---:|
| Local runtime | Yes | Optional | Optional | Optional |
| Hosted runtime | No | Yes | Yes | Yes / private |
| BYO model keys | Yes | Yes | Yes | Yes |
| Managed inference wallet | No | Yes | Yes | Yes |
| Cloud sync across devices | No | Yes | Yes | Yes |
| Backups / restore | Self-managed | Yes | Yes | Yes |
| Single-user private workspace | Yes | Yes | Yes | Yes |
| Team workspace | No | No | Yes | Yes |
| Member invites | No | No | Yes | Yes |
| Shared playbook registry | Export/import only | No | Yes | Yes |
| Review / approval flow | No | No | Yes | Yes |
| RBAC | No | No | Limited / Yes | Yes |
| SSO / SCIM | No | No | No / Later | Yes |
| Audit logs | No | Minimal | Team-level | Full |
| Hosted eval jobs | No / local only | Yes | Yes | Yes |
| Self-hosted control plane | Yes, self-managed | No | No | Yes |
| SLA / support | Community | Standard | Priority | Contractual |

### 3.2 What users pay for

#### ACE OSS
Users pay with their own setup effort and operations burden.

#### ACE Cloud Personal
Users pay for convenience:

- no setup burden
- hosted storage and backups
- sync across machines
- hosted evals and background tasks
- managed inference and billing simplicity

#### ACE Cloud Team
Users pay for coordination:

- shared workspaces
- team playbook lifecycle
- reviews, permissions, and accountability

#### ACE Enterprise
Users pay for governance and procurement alignment:

- private deployment options
- compliance controls
- identity management
- contractual support

### 3.3 Pricing direction (non-final)

This spec does not set prices, but it recommends the shape:

- **Cloud Personal:** flat monthly fee with included usage and optional overages
- **Cloud Team:** base workspace fee plus seats and higher usage envelope
- **Enterprise:** annual contract with deployment, support, and governance terms

---

## 4. User Segments and Jobs to Be Done

### Segment A — Local-first builder

**Who:** developer, researcher, or tinkerer who wants control and low cost  
**Primary job:** run ACE locally, inspect behavior, bring own keys, keep full control  
**Why they matter:** they drive adoption, word-of-mouth, and technical credibility

### Segment B — Hosted solo power user

**Who:** individual who wants ACE value without running infrastructure  
**Primary job:** get sync, backups, web access, managed inference, and a smoother UX  
**Why they matter:** they are the bridge between free adoption and revenue

### Segment C — Small team using agents collaboratively

**Who:** startup or engineering team experimenting with shared agent workflows  
**Primary job:** share playbooks, review changes, align behavior across multiple users and agents  
**Why they matter:** they create expansion revenue and stronger retention

### Segment D — Enterprise platform owner

**Who:** internal platform, security, or enablement team  
**Primary job:** adopt ACE with compliance, identity, auditability, and deployment controls  
**Why they matter:** they drive larger contracts and durable revenue

---

## 5. Scope and Non-Goals

### In Scope for this next iteration

- define and implement the OSS/core versus cloud boundary
- preserve a real Cloud Personal plan
- introduce a workspace-based entitlement model
- support cloud sync, backups, and hosted evals
- add self-setup and benchmark-oriented onboarding
- prepare for Codex/OpenAI OAuth as an onboarding and inference convenience layer
- create migration support for existing hosted solo users

### Out of Scope for initial implementation

- fully custom enterprise RBAC in v1
- broad connector marketplace in the first pass
- complex billing permutations before usage is understood
- full marketplace/community ecosystem before core packaging is stable
- large-scale enterprise self-hosting before Cloud Personal and Team are solid

### Explicit Non-Goal

Do **not** ship an open-source version that only appears open but is not practically useful.

---

## 6. Functional Requirements

### 6.1 ACE OSS Requirements

The open-source edition must support a complete local single-user workflow.

#### Required capabilities

- local install and configuration
- local storage for playbooks and metadata
- CLI access
- local API server
- local MCP server
- import/export of playbooks and traces
- direct provider integrations with user-supplied credentials
- local evals and benchmarking
- documentation and templates sufficient for self-serve adoption

#### Nice-to-have capabilities

- one-command setup
- starter project templates
- demo repo and seeded playbook packs

### 6.2 ACE Cloud Personal Requirements

The hosted personal plan must deliver clear individual value beyond the OSS version.

#### Required capabilities

- hosted account and workspace
- cloud sync across machines and sessions
- hosted storage and backups
- web dashboard
- personal usage analytics
- managed inference wallet or provider connection
- hosted eval runs and scheduled background jobs
- seamless upgrade path from personal to team

### 6.3 ACE Cloud Team Requirements

The team plan adds collaboration and administration.

#### Required capabilities

- multi-member workspace
- member invites
- shared playbook registry
- workspace-wide history
- review and approval workflow for promoted playbook changes
- basic roles and permissions
- admin usage visibility

### 6.4 Enterprise Requirements

- SSO / identity provider integration
- audit logs
- advanced policy controls
- optional self-hosted control plane
- support for procurement and compliance workflows

### 6.5 Onboarding Requirements

ACE should reduce setup friction dramatically.

#### Target workflow

1. user installs ACE
2. user runs `ace init`
3. ACE detects or asks for environment details
4. `ace doctor` validates missing dependencies and config
5. `ace seed` creates initial playbooks from repo/docs/examples
6. `ace benchmark` demonstrates measurable value
7. user either continues locally or upgrades to hosted cloud mode

### 6.6 OAuth / Inference Requirements

A hosted integration path should support:

- sign-in and session creation
- managed inference access for cloud users
- provider abstraction so ACE does not become tightly locked to one vendor
- usage metering and entitlement-aware routing

---

## 7. Technical Architecture

### 7.1 Architectural Principle

**Premium enforcement must happen server-side.**

Bad boundary:

- hiding premium buttons in UI only
- checking a local boolean license flag
- depending on obfuscation

Good boundary:

- premium action calls a private ACE Cloud service
- ACE Cloud checks auth, workspace, plan, entitlements, and usage
- server allows or denies the request

### 7.2 Recommended layers

#### Public layer: `ace-core`

Contains:

- playbook domain logic
- retrieval / refinement abstractions
- local runtime orchestration
- interfaces for storage, sync, inference, evals, and entitlements

#### Public layer: local implementations

Contains:

- local filesystem or SQLite / Postgres store
- local direct provider gateway
- local eval runner
- no-op or export-based sync

#### Private layer: ACE Cloud services

Contains:

- auth/session service
- workspace service
- entitlements service
- sync service
- hosted eval worker service
- billing and usage metering
- managed inference gateway
- admin and analytics services

### 7.3 Interface model

The OSS core should talk to abstractions, not directly to hosted code.

```ts
export interface PlaybookStore {
  get(id: string): Promise<Playbook | null>;
  put(playbook: Playbook): Promise<void>;
  list(scope: Scope): Promise<Playbook[]>;
}

export interface SyncBackend {
  push(events: SyncEvent[]): Promise<void>;
  pull(cursor?: string): Promise<SyncBatch>;
}

export interface InferenceGateway {
  call(request: ModelRequest): Promise<ModelResponse>;
}

export interface EvalRunner {
  run(spec: EvalSpec): Promise<EvalResult>;
}

export interface Entitlements {
  can(feature: Feature): Promise<boolean>;
}
```

### 7.4 Recommended repository split

#### Public repository

- `packages/ace-core`
- `packages/ace-cli`
- `packages/ace-local-server`
- `packages/ace-mcp`
- `packages/ace-protocol`
- `packages/ace-provider-*`
- `examples/`
- `docs/`

#### Private repository

- `services/auth`
- `services/workspaces`
- `services/entitlements`
- `services/sync-api`
- `services/eval-workers`
- `services/billing`
- `services/inference-gateway`
- `apps/cloud-dashboard`
- `packages/ace-cloud-sdk`

### 7.5 Suggested hosted API surface

```text
POST   /v1/auth/login
POST   /v1/auth/logout
GET    /v1/me
GET    /v1/workspaces/:id
GET    /v1/workspaces/:id/entitlements
GET    /v1/workspaces/:id/usage
POST   /v1/workspaces/:id/sync/push
GET    /v1/workspaces/:id/sync/pull
POST   /v1/workspaces/:id/evals/run
GET    /v1/workspaces/:id/evals/:run_id
POST   /v1/workspaces/:id/invitations
GET    /v1/workspaces/:id/playbooks
POST   /v1/workspaces/:id/playbooks/promote
POST   /v1/workspaces/:id/inference
```

---

## 8. Data Model and Entitlements

### 8.1 Core entities

#### Workspace

The primary tenancy object.

```ts
interface Workspace {
  id: string;
  name: string;
  plan: "personal" | "team" | "enterprise";
  deploymentMode: "cloud" | "self_hosted";
  seatLimit: number;
  entitlements: WorkspaceEntitlements;
  usageLimits: UsageLimits;
}
```

#### Membership

```ts
interface Membership {
  workspaceId: string;
  userId: string;
  role: "owner" | "member" | "reviewer" | "admin";
}
```

#### Subscription

```ts
interface Subscription {
  workspaceId: string;
  billingProvider: "stripe" | "manual";
  status: "trialing" | "active" | "past_due" | "canceled";
  planCode: string;
}
```

#### Entitlements

```ts
interface WorkspaceEntitlements {
  cloudSync: boolean;
  hostedBackups: boolean;
  managedInference: boolean;
  hostedEvals: boolean;
  inviteMembers: boolean;
  sharedWorkspace: boolean;
  approvals: boolean;
  rbac: boolean;
  sso: boolean;
  auditLogs: boolean;
}
```

### 8.2 Plan semantics

#### Personal workspace

- seat limit = 1
- cloud convenience features enabled
- collaboration features disabled

#### Team workspace

- seat limit > 1
- cloud convenience features enabled
- collaboration features enabled

#### Enterprise workspace

- team capabilities plus governance and deployment controls

### 8.3 Example entitlement evaluation

```ts
function canUseFeature(workspace: Workspace, feature: keyof WorkspaceEntitlements) {
  return workspace.entitlements[feature] === true;
}
```

### 8.4 Migration requirement

Existing hosted solo customers must be migrated into **Cloud Personal workspaces** without losing data or changing core workflows.

---

## 9. Developer Task Breakdown

This section is structured to be directly broken into issues, milestones, or AI coding-agent prompts.

### Epic 0 — Spec, repo hygiene, and delivery scaffolding

**Goal:** prepare the codebase and planning artifacts so implementation can happen in a clean, incremental way.

- [ ] **E0-T1** Create a `next-iteration` branch or working stream for the platform split.
  - Deliverables: branch strategy, changelog note, migration draft.
  - Acceptance criteria: all work for the new architecture lands behind a clear branch or feature gating model.

- [ ] **E0-T2** Create an architecture decision record (ADR) covering the OSS/core versus cloud boundary.
  - Deliverables: ADR markdown file.
  - Acceptance criteria: document explicitly states what code is public, what services are private, and why.

- [ ] **E0-T3** Create issue templates for epics, implementation tasks, and migration tasks.
  - Deliverables: GitHub issue templates or internal equivalents.
  - Acceptance criteria: future tasks can be generated consistently by humans or AI agents.

### Epic 1 — Extract and harden the OSS core

**Goal:** produce a clean, reusable local runtime with no cloud dependency.

- [ ] **E1-T1** Create `ace-core` as the shared domain package.
  - Deliverables: package structure, build configuration, tests.
  - Acceptance criteria: package builds independently and has no imports from private cloud code.

- [ ] **E1-T2** Define interfaces for storage, sync, inference, evals, and entitlements.
  - Deliverables: core interface definitions and docs.
  - Acceptance criteria: local and cloud implementations can satisfy the same contracts.

- [ ] **E1-T3** Move playbook domain logic into `ace-core`.
  - Deliverables: migrated modules, backward-compatible adapters where needed.
  - Acceptance criteria: existing local workflows still function via the new package.

- [ ] **E1-T4** Add local implementations for `PlaybookStore`, `InferenceGateway`, and `EvalRunner`.
  - Deliverables: filesystem / SQLite store, direct provider gateway, local eval runner.
  - Acceptance criteria: a single user can install and use ACE with no cloud account.

- [ ] **E1-T5** Add import/export support for playbooks and traces.
  - Deliverables: stable file formats, CLI commands.
  - Acceptance criteria: users can move artifacts between local and hosted contexts.

- [ ] **E1-T6** Add integration tests covering a fully local happy path.
  - Deliverables: end-to-end local test flow.
  - Acceptance criteria: CI proves local ACE can ingest, persist, retrieve, and execute playbooks.

### Epic 2 — Define the workspace model and entitlement system

**Goal:** create one tenancy model that supports both hosted personal and hosted team plans.

- [ ] **E2-T1** Design the `Workspace`, `Membership`, `Subscription`, and `Entitlement` schemas.
  - Deliverables: schema definitions, migrations.
  - Acceptance criteria: model supports `personal`, `team`, and `enterprise` plans without branching the app.

- [ ] **E2-T2** Build a workspace service.
  - Deliverables: CRUD APIs, membership management, workspace bootstrap flow.
  - Acceptance criteria: every cloud user belongs to exactly one or more workspaces.

- [ ] **E2-T3** Build an entitlements service.
  - Deliverables: plan-to-entitlement mapping, usage limits, API endpoint.
  - Acceptance criteria: cloud clients can fetch authoritative feature access from the server.

- [ ] **E2-T4** Add middleware for server-side entitlement checks.
  - Deliverables: shared authorization helper.
  - Acceptance criteria: premium endpoints reject unauthorized requests even if the client is modified.

- [ ] **E2-T5** Add feature-flag support for gradual rollout.
  - Deliverables: environment-aware rollout controls.
  - Acceptance criteria: new plans and capabilities can be enabled for selected users before GA.

### Epic 3 — Build ACE Cloud Personal foundation

**Goal:** make the hosted individual plan clearly better than OSS for users who want convenience.

- [ ] **E3-T1** Implement hosted account/session flow.
  - Deliverables: login, logout, session refresh, user profile endpoints.
  - Acceptance criteria: a personal user can securely sign into ACE Cloud.

- [ ] **E3-T2** Implement a personal workspace bootstrap flow.
  - Deliverables: automatic creation of a one-seat workspace on signup.
  - Acceptance criteria: new hosted personal users land in a usable workspace with correct entitlements.

- [ ] **E3-T3** Build cloud sync for single-user workspaces.
  - Deliverables: sync event format, push/pull APIs, conflict strategy.
  - Acceptance criteria: a personal user can move across devices without losing playbooks or history.

- [ ] **E3-T4** Add backups and restore for hosted personal data.
  - Deliverables: backup jobs, restore path, admin tooling.
  - Acceptance criteria: hosted personal workspaces can be restored after data loss scenarios.

- [ ] **E3-T5** Build a minimal web dashboard for personal users.
  - Deliverables: dashboard pages for playbooks, activity, usage, and settings.
  - Acceptance criteria: the dashboard supports the main hosted personal workflow end to end.

- [ ] **E3-T6** Add hosted eval runs for personal users.
  - Deliverables: job queue, run detail UI/API, result storage.
  - Acceptance criteria: hosted personal users can launch evals without running local infrastructure.

### Epic 4 — Billing, usage metering, and managed inference

**Goal:** monetize hosted convenience cleanly for personal and team plans.

- [ ] **E4-T1** Implement a subscription service and billing integration.
  - Deliverables: plan catalog, subscription state sync, webhook handling.
  - Acceptance criteria: workspace plan state updates automatically from billing events.

- [ ] **E4-T2** Implement usage metering.
  - Deliverables: storage counters, eval counters, managed inference counters.
  - Acceptance criteria: the platform can show usage and enforce soft or hard limits.

- [ ] **E4-T3** Build a managed inference gateway.
  - Deliverables: server-side model routing endpoint, provider adapters, logging.
  - Acceptance criteria: eligible cloud users can invoke managed inference without exposing provider keys in the client.

- [ ] **E4-T4** Add BYO-provider and managed-provider modes.
  - Deliverables: config paths for both modes.
  - Acceptance criteria: users can choose between their own keys and ACE-managed inference where supported.

- [ ] **E4-T5** Add plan-aware usage UI.
  - Deliverables: usage dashboard and upgrade prompts.
  - Acceptance criteria: users understand what is included, what is consumed, and what happens at limits.

### Epic 5 — Team collaboration layer

**Goal:** add collaboration on top of the hosted personal foundation without complicating the solo path.

- [ ] **E5-T1** Implement team workspace creation and upgrade path from personal.
  - Deliverables: upgrade flow, workspace conversion logic.
  - Acceptance criteria: a personal workspace can become a team workspace without data loss.

- [ ] **E5-T2** Add member invitations and membership management.
  - Deliverables: invite workflow, acceptance flow, removal flow.
  - Acceptance criteria: owners can invite and manage members inside team workspaces.

- [ ] **E5-T3** Build the shared playbook registry.
  - Deliverables: team-visible playbook catalog, ownership metadata.
  - Acceptance criteria: members can discover and reuse approved team playbooks.

- [ ] **E5-T4** Add review and approval flow for promoted playbooks.
  - Deliverables: review states, approval actions, activity history.
  - Acceptance criteria: a team can distinguish draft, proposed, approved, and archived playbook states.

- [ ] **E5-T5** Implement basic roles and permissions.
  - Deliverables: owner/member/reviewer/admin role behavior.
  - Acceptance criteria: only authorized members can approve, manage seats, or alter shared workspace settings.

### Epic 6 — Self-setup and time-to-value improvements

**Goal:** reduce activation friction for new users and make ACE easier for AI agents to set up.

- [ ] **E6-T1** Implement `ace init`.
  - Deliverables: guided project bootstrap, default config generation.
  - Acceptance criteria: a new user can initialize ACE in one command.

- [ ] **E6-T2** Implement `ace doctor`.
  - Deliverables: environment validation and remediation hints.
  - Acceptance criteria: missing dependencies, invalid config, and unsupported setups are clearly surfaced.

- [ ] **E6-T3** Implement `ace seed`.
  - Deliverables: repo/doc/example scanning and initial playbook generation.
  - Acceptance criteria: a fresh project receives a useful starter playbook set.

- [ ] **E6-T4** Implement `ace benchmark`.
  - Deliverables: benchmark runner and result summary.
  - Acceptance criteria: user can compare baseline versus ACE-assisted results quickly.

- [ ] **E6-T5** Add an “agent setup mode” optimized for AI coding agents.
  - Deliverables: deterministic CLI flow, non-interactive flags, machine-readable output.
  - Acceptance criteria: a coding agent can install and configure ACE without manual intervention.

### Epic 7 — Open-source packaging and distribution

**Goal:** make ACE OSS easy to adopt and share without eroding the hosted moat.

- [ ] **E7-T1** Choose and apply the OSS license for the public engine.
  - Deliverables: license decision, contributor guidance.
  - Acceptance criteria: public repo is legally clean and aligned with the business model.

- [ ] **E7-T2** Publish a dedicated OSS repository or clean public package structure.
  - Deliverables: public repo layout, README, install docs.
  - Acceptance criteria: an external user can understand what is open, what is hosted, and how to start.

- [ ] **E7-T3** Create sample projects and example playbook packs.
  - Deliverables: starter repo or examples directory.
  - Acceptance criteria: new OSS users can demonstrate value quickly.

- [ ] **E7-T4** Add docs explaining the product split.
  - Deliverables: “OSS vs Cloud Personal vs Team vs Enterprise” documentation.
  - Acceptance criteria: the distinction is obvious and reduces confusion.

### Epic 8 — OAuth and hosted identity integrations

**Goal:** reduce friction for hosted usage and create a path for managed inference tied to authenticated accounts.

- [ ] **E8-T1** Design the identity abstraction layer.
  - Deliverables: provider-neutral auth interface.
  - Acceptance criteria: ACE can add OAuth providers without deeply coupling the application.

- [ ] **E8-T2** Implement the first hosted OAuth provider flow.
  - Deliverables: OAuth callback flow, session creation, secure token storage.
  - Acceptance criteria: users can sign into ACE Cloud via the chosen provider.

- [ ] **E8-T3** Connect identity to managed inference entitlements.
  - Deliverables: account linking and entitlement checks.
  - Acceptance criteria: only authorized plans can use managed inference routes.

- [ ] **E8-T4** Add fallback local auth / API-key mode for users who do not want hosted OAuth.
  - Deliverables: alternative onboarding path.
  - Acceptance criteria: ACE remains provider-neutral and local-friendly.

### Epic 9 — Migration, analytics, and launch readiness

**Goal:** ship the transition without breaking current users and with enough instrumentation to learn quickly.

- [ ] **E9-T1** Migrate existing hosted solo users to `personal` workspaces.
  - Deliverables: migration script, rollback plan, validation checks.
  - Acceptance criteria: existing users keep data, access, and billing state.

- [ ] **E9-T2** Add product analytics for activation and conversion.
  - Deliverables: event taxonomy and instrumentation.
  - Acceptance criteria: team can observe signup, init, seed, benchmark, upgrade, and retention behavior.

- [ ] **E9-T3** Add operational dashboards for cloud health.
  - Deliverables: sync health, job queue health, inference gateway health.
  - Acceptance criteria: hosted services can be monitored during rollout.

- [ ] **E9-T4** Publish release notes and migration communication.
  - Deliverables: user-facing release messaging.
  - Acceptance criteria: customers understand the new plans and how they benefit.

---

## 10. Recommended Release Plan

### Phase 1 — Foundation

Ship first:

- Epic 1 (OSS core)
- Epic 2 (workspaces and entitlements)
- selected parts of Epic 3 (auth + personal workspace bootstrap)

**Exit criteria:** one codebase can support local and hosted modes with a clean boundary.

### Phase 2 — Cloud Personal upgrade

Ship next:

- remaining Epic 3
- Epic 4
- Epic 9 migration work

**Exit criteria:** hosted personal plan is clearly valuable and current solo customers are safely migrated.

### Phase 3 — Activation and OSS growth

Ship next:

- Epic 6
- Epic 7
- initial Epic 8 work

**Exit criteria:** new users can adopt ACE locally or in the cloud with much lower friction.

### Phase 4 — Team collaboration

Ship next:

- Epic 5
- remaining Epic 8 work where relevant

**Exit criteria:** team workspaces, invites, and shared playbook workflows are stable enough for active paid use.

### Phase 5 — Enterprise hardening

Ship later:

- enterprise controls, audit logs, SSO, self-hosted control plane packaging

**Exit criteria:** ACE can support more complex procurement and security requirements.

### Recommended build order summary

1. core boundary
2. workspace model
3. hosted personal plan
4. billing and inference
5. self-setup and OSS distribution
6. team workflows
7. enterprise controls

---

## 11. Success Metrics

### Product metrics

- time from install/signup to first successful ACE run
- time from first run to first saved playbook
- time from first run to first benchmark result
- rate of upgrade from free/local user to hosted personal
- rate of upgrade from hosted personal to team

### Business metrics

- monthly growth in active paying personal users
- expansion revenue from team upgrades
- retention of existing hosted solo users after migration
- conversion rate from OSS adoption to hosted signup

### Reliability metrics

- cloud sync success rate
- hosted eval completion rate
- inference gateway success rate
- restore success rate for hosted backups

---

## 12. Risks and Open Questions

### Risks

#### Risk 1 — The OSS version becomes too weak

If the open-source engine feels crippled, it will not generate trust or adoption.

**Mitigation:** ensure single-user local workflows are complete and valuable.

#### Risk 2 — The cloud product feels like “just hosting” without enough value

If Cloud Personal only removes setup burden but does not improve daily workflow, conversion may remain weak.

**Mitigation:** include sync, backups, hosted evals, managed inference, and strong UX.

#### Risk 3 — Team features arrive before the hosted personal plan is strong

This could create complexity before the core monetization layer is stable.

**Mitigation:** prioritize personal hosted value first.

#### Risk 4 — Identity and provider coupling becomes too tight

A single provider-specific auth design could make the product harder to evolve.

**Mitigation:** build an identity abstraction layer and preserve local/BYO paths.

### Open Questions

1. Which license best fits ACE OSS?
2. Should Cloud Personal include some hosted eval allowance by default?
3. Should managed inference be included in plan pricing or sold as credits?
4. What should the first default OAuth provider be?
5. Which artifacts should sync between local and cloud by default versus opt-in?
6. Should team approvals be lightweight at first or modeled as a more formal review system?

---

## 13. Appendix: Suggested Package and Service Layout

### Public packages

```text
packages/
  ace-core/
  ace-cli/
  ace-local-server/
  ace-mcp/
  ace-protocol/
  ace-provider-openai/
  ace-provider-anthropic/
examples/
  starter-project/
  benchmark-demo/
docs/
  oss-overview.md
  local-quickstart.md
```

### Private cloud services

```text
services/
  auth/
  workspaces/
  entitlements/
  sync-api/
  eval-workers/
  billing/
  inference-gateway/
apps/
  cloud-dashboard/
packages/
  ace-cloud-sdk/
```

### First dashboard views

- Home / activity
- Playbooks
- Benchmarks / eval runs
- Usage
- Billing
- Members (team only)
- Settings

### Suggested first milestone for execution

If only one milestone is executed immediately, it should be:

1. extract the local OSS core  
2. add workspace and entitlement primitives  
3. ship Cloud Personal with sync, backups, and hosted evals  
4. migrate existing hosted solo users safely

That sequence preserves current revenue while unlocking the broader product strategy.

---

## Final Recommendation

ACE should be built as **one core product with multiple deployment and collaboration modes**, not as separate disconnected products.

The next iteration should prioritize:

- a strong open-source local runtime
- a durable Cloud Personal plan for solo users
- a clean hosted upgrade path into team collaboration
- server-side enforcement of premium features through private cloud services
- activation improvements that let both humans and AI agents adopt ACE with far less friction

This is the product direction most likely to improve both **adoption** and **revenue** while preserving architectural coherence.
