# ADR-0002: Owner-selectable Shell execution profiles

- Status: **Proposed**
- Date: 2026-11-20

## Context

Some users insist that only independently authorized local Jan/Qwen may invoke Shell; others explicitly want to permit cloud-driven coding agents to use terminal tools. A universal mandatory "local only" rule would exclude the latter, while default cloud host Shell would violate privacy-first expectations.

## Decision

Provide an owner-controlled execution-profile selector independent of AUTO/ECONOMY/PERFORMANCE routing. **Default LOCAL_ISOLATED** with trusted local worker; **HYBRID_PRIVATE** for cloud reasoning with local Shell; **CLOUD_SHELL_APPROVAL** for individually scoped live approvals in an isolated sandbox; **CLOUD_SHELL_TRUSTED** for short-lived revocable preapproved sandbox scopes.

A "cloud Shell" request means the cloud model may choose/request operations but only a **broker-controlled, separately sandboxed runtime** actually executes them. It never grants unrestricted host-level Shell or automatic release of raw stdout. All modes require authenticated authority and independently verified boundaries. Changing routing mode never changes permission mode.

## Consent

Grant bound to exact task, recipient model/provider, workspace alias, allowed operations, max calls, expiry and disclosure scope; revocable and replay-resistant. GUI must show scope, recipient and risks. If identity or broker is unavailable, deny/hold. No model-generated consent fields.

## Rejected

- Unlimited cloud Shell by default.
- Local-model-only inference forced on all users.
- Reusing OpenCode agent names as authentication.
- Using prompt instructions, Kandev stage labels or Langflow nodes as sole enforcement.

## Pending

Threat model validation, disposable sandbox implementation, trusted authorization UX, persistent replay/consent store, output filtering and operator acceptance.
