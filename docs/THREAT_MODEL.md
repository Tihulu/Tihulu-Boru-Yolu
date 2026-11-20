# Threat model (design stage)

## Assets

Local private source, personal documents, Jan/OpenCode config and chat state, provider API credentials, filesystem, system processes, GPU memory, third-party project repositories, approval decisions, audit logs and integrity of task status.

## Trust boundaries

1. Browser/UI -> Kandev/Langflow (authentication and CSRF/session handling).
2. Kandev/Langflow -> Boru Adapter (typed request, auth, replay protection).
3. Router -> cloud model (only approved minimal payload, never leaked secrets).
4. Router -> trusted broker (separate service, authenticated caller).
5. Broker -> isolated executor/sandbox (OS-enforced scope, no inherited host privilege).
6. Executor -> Privacy Bridge -> model (allowlisted result schema and provenance).
7. Local service -> GitHub (user-approved public artifacts, no private inventory).

## Main threats and mitigations

| Threat | Required mitigation |
| --- | --- |
| Prompt injection asks an agent to enable Shell or reveal secrets | Never accept model text as authorization; broker enforces capabilities |
| Kandev agent defaults to host-level Shell | Disposable workspace, explicit runtime/profile review, deny native host tools until approved |
| Langflow custom Python component opens files or internet | Disable/contain component runtime in restricted profile; OS isolation and file-access settings |
| Cloud model given "Shell permission" sees private host paths | Confined sandbox, explicit mount allowlists, no home/Jan/OpenCode mounts, output release gate |
| Fake local-model identity or forged consent | Host-authenticated worker identity and local authority-signed, recipient-bound grants |
| Stale/replayed approval | Persistent atomic nonce and revocation state |
| Leaking terminal output through error messages, tracing or task summaries | Default deny all untyped fields; local redaction before any model request, sanitized errors |
| Tool result contains extra JSON keys or nested payload | Strict schema validation and size/cardinality limits |
| Race between approved path and file access | Directory file descriptors, no-follow semantics and OS-level confinement; path normalization alone is insufficient |
| Unsafe fallback from local to cloud | Authorization and disclosure filters apply to *every* dispatch including retries |
| Compromised LAN listener | Loopback by default, no public port; authenticated TLS proxy only with separate approval |
| Resource exhaustion / swap thrash | Bounded agents, memory leases, cgroups/job quotas where available, timeouts |
| Supply-chain compromise during install | Pin upstream version, validate official origin/checksums, no unreviewed pipe-to-shell |
| Agent accidentally alters live user sessions | Separate pilot state/worktrees; no production config writes; rollback checkpoints |

## Cloud Shell risk acknowledgment

Enabling cloud-driven Shell grants **additional control to a remote model** and can expose some information through task outputs. Even in an isolated sandbox, it is not safe to assume absolute containment. Users must see an explicit warning and current scope, and be able to cancel/revoke; it must never activate because AUTO/PERFORMANCE selected a cloud provider.

## Out of scope for v1

Unrestricted root/host Shell for cloud agents, unreviewed third-party executable plugins, exposed multi-tenant deployment, access to host docker.sock, automatic escalation on errors, and public internet hosting without formal security review.

## Security test gates

Dynamic sandbox breakout attempts, malicious filenames, secret exfiltration attempts, local network/metadata service access, symlink traversal, consent replay/forgery, cancellation races, quotas, model instruction override and error-path disclosure. Conduct tests in disposable hosts only.
