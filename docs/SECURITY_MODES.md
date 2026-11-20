# Execution policies, user-controlled Shell and consent

**Preservation requirement:** [ADR-0004](ADRS/0004-preserve-modes-and-privacy.md) locks the original optimization, privacy and Shell profiles during the Boru Core independence refactor. No mode changes privileges implicitly.

## Product principle

The **owner chooses** whether a cloud model may drive Shell tasks. This is a legitimate feature, not a permission bypass. The choice must be **explicit, scoped, revocable and enforced outside the model**. The default always remains local-isolated.

There are **three independent axes**:

1. `inference_scope`: `LOCAL_ONLY` or `CLOUD_ALLOWED`.
2. `execution_profile`: `LOCAL_ISOLATED`, `HYBRID_PRIVATE`, `CLOUD_SHELL_APPROVAL` or `CLOUD_SHELL_TRUSTED`.
3. `disclosure_policy`: `MINIMUM_NECESSARY` or `SCOPED_APPROVED`.

`AUTO`/`ECONOMY`/`BALANCED`/`PERFORMANCE`/`MANUAL` tune efficiency and quality **without changing access rights**. A quota fallback must not silently change any of these three axes.

## Profile matrix

| Profile | Who decides commands? | Where do commands run? | Approval | Host files | Raw output to cloud |
| --- | --- | --- | --- | --- | --- |
| LOCAL_ISOLATED (default) | Local authorized worker | Local confined executor | Owner-authorized operation scope | Specific allowed targets only | No |
| HYBRID_PRIVATE | Local worker after cloud suggests a typed task | Local confined executor | Owner-authorized local scope | Specific allowed targets only | No |
| CLOUD_SHELL_APPROVAL | Cloud model may propose/direct a specific operation | **Separate, isolated project sandbox via broker** | Live, scoped owner consent | Explicit sandbox mounts only | No by default; separate approved disclosure |
| CLOUD_SHELL_TRUSTED (advanced) | Cloud model may direct allowlisted sandbox operations | Same isolated sandbox and broker | Owner-issued **expiring scoped session grant** | Explicit sandbox mounts only | No by default; separate approved disclosure |

"Trusted" is not unrestricted host/root Shell and not a provider exemption. Unrestricted cloud-driven host execution is deliberately out of scope in v1.

## Cloud Shell experience

1. Owner deliberately selects a cloud-enabled execution profile (never selected automatically by router or model).
2. UI displays exact provider/model, workspace alias, sandbox type, allowed operations, filesystem mounts, network egress, duration, maximum calls and output-release policy.
3. Owner approves through an authenticated local UI; a **trusted local authority** creates a non-forgeable, request-bound capability. A model-provided `owner_consent=true` is invalid.
4. Broker verifies actor, capability, resource scope, expiry, call budget and sandbox availability **for every operation**.
5. A sandboxed process executes; the model cannot access native host Shell, arbitrary Docker socket, secrets, home directory, Jan data or OpenCode configs.
6. Broker classifies and restricts output before returning any result to cloud.
7. Owner can immediately revoke, cancel queued work and terminate only broker-owned jobs; record a sanitized audit event.

The implementation may use carefully restricted disposable containers or another OS-level isolation primitive verified on Pop!_OS/Ubuntu. **Container isolation alone is not a guarantee against hostile code**. Disallow privileged containers, host PID/network, unrestricted host mounts and Docker socket passthrough.

## Policy defaults

- Default: `LOCAL_ISOLATED` + `MINIMUM_NECESSARY`, default inference controlled separately.
- Network egress from execution sandbox **off** until explicitly approved.
- No silent "always allow" based on accepting one previous prompt.
- Never turn a provider error, quota limit, timeout, missing executor or denial into broader permissions.
- No remote API / public LAN binding without an authenticated reverse proxy, TLS, operator approval and threat-model review.
- Never allow another local AI's free-text assertion to satisfy identity or consent checks.
- Security/consent event logs kept locally; do not push them to GitHub.
- Cloud model's ability to request Shell does not imply it may receive private files or raw terminal output.

## Consent grant contract (design; not implemented)

Capability fields: `grant_id`, authenticated `owner_id`, `recipient_provider`, `recipient_model`, `task_id`, `sandbox_id`, exact allowed `operation_types`, `resource_aliases`, `field_disclosures`, `issued_at`, `expires_at`, `max_calls`, `nonce`, `policy_revision` and cryptographic authenticity proof.

Denials: no grant, wrong recipient, wrong task, stale revision, expired/revoked token, replay, malformed schema, non-allowlisted output, missing sandbox, failing worker authentication, excessive resource use.

Treat authorization and *disclosure* as separate decisions. Consent for an operation never implies consent to transmit its raw stdout.

## Safety tests required before rollout

- Model switches without expanding permissions.
- CLOUD_ALLOWED + LOCAL_ISOLATED retains local Shell boundary.
- LOCAL_ONLY + cloud Shell profile is rejected as an inconsistent policy.
- Cloud Shell without grant/after expiry/revocation/replay is denied.
- Identical user-approved flow with no sandbox is denied.
- Prompt injection inside a retrieved file or agent response cannot grant capabilities.
- Sandbox cannot reach private host paths, Jan databases, other active OpenCode sessions, credentials or unrelated services.
- Extra sensitive disclosure requires a **new, specific approval**.
- A blocked provider or disabled bridge never falls back to unrestricted host Shell.

All above are **design acceptance requirements**, not claims of passing implementation.
