# ADR-0003: Boru Core independence and optional legacy TIHULU-AUTO

- Status: **Proposed — supersedes the routing-owner clause in ADR-0001**
- Date: 2026-11-20

## Context

TIHULU-AUTO is a separate, unfinished subagent-orchestration project. An earlier Boru Yolu draft made it the mandatory routing authority, which would block the larger Boru Yolu platform whenever TIHULU-AUTO was unavailable or incomplete. The user explicitly requires OpenCode and Jan to remain standalone and not depend on either project.

## Decision

1. Build **Boru Core** as Boru Yolu's *native, self-contained* orchestration engine: provider registry, model selection, budgets, DAG scheduling, child-session tracking, resource leases and verified results.
2. **Boru Core must have no runtime, build, install, test or release dependency on TIHULU-AUTO.** TIHULU-AUTO is an opt-in legacy adapter/migration source only; disabled by default, with isolated credentials and no shared mutable configuration.
3. Treat **OpenCode as a standalone external coding-agent application**. Connect only through a supported, optional adapter. A Boru failure cannot modify or stop OpenCode sessions; OpenCode may be used with no Boru components installed.
4. Treat **Jan as a standalone local inference service**. Boru Core can use Jan's supported API directly, without requiring OpenCode, Kandev, Langflow or TIHULU-AUTO.
5. Treat Kandev and Langflow as optional UI/workflow surfaces rather than prerequisites for the minimal Boru Core text-only runtime.
6. The trusted local policy broker and privacy gate remain independently enforced; no adapter may bypass consent or disclosure policy.
7. Importing existing TIHULU-AUTO workflows/configuration or moving agents is a separate explicit, reversible migration requiring owner approval and tests. No automatic takeover or credential copying.
8. Maintain versioned integration contracts, original decisions in Git history and test evidence; **M1–M8 must not be gated on TIHULU-AUTO's completion**.

## Independent lifecycle and minimum startup

- OpenCode works as-is with Boru and TIHULU-AUTO both stopped, absent or uninstalled.
- Jan works as-is with Boru and TIHULU-AUTO both stopped, absent or uninstalled.
- Boru Core can start without Kandev/Langflow/OpenCode/TIHULU-AUTO and perform a synthetic, authorized text-only local Jan inference when Jan is available.
- Loss of any optional adapter fails only the affected adapter: no model substitution involving more private-data disclosure, no extra Shell permissions and no crashes of standalone services.

## Alternatives

- Reuse TIHULU-AUTO as Boru's required orchestrator: **rejected** because unfinished and violates independent release goals.
- Make OpenCode or Jan child processes managed exclusively by Boru: **rejected** because stable-first independent operation is a core requirement.
- Duplicate multiple authoritative routers in Kandev, Langflow and Boru: **rejected** because task ownership and permissions would diverge.

## Acceptance evidence required

- Run Boru Core with TIHULU-AUTO absent; independently prove direct Jan text-only model call with observed provider/model.
- Verify existing OpenCode projects and Jan services start, stop and operate independently, with no global configuration mutation.
- Verify optional OpenCode child-session integration without relying on TIHULU-AUTO-specific agents or skills.
- Simulate missing/failed legacy adapters and demonstrate Boru continues for supported tasks.
- Verify rollback removes only Boru-owned services and configuration.

**Status:** architecture decision only; none of these runtime acceptance tests are claimed to have passed yet.
