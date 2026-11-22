# AI Provider Connections — capability, authentication and entitlement matrix

This document is the **phase 1 deliverable of issue #10** (extended by #11): a
capability/auth/billing matrix plus a secret-free example configuration. It
describes what is *supported by code* versus what is *owner-gated*, and it
never asserts that any provider has been connected.

**Signing in is not inference authorization.** An authenticated identity grants
an identity; model inference requires an authorized model call, and
subscription usage is a separate entitlement that must be observed rather than
assumed. Boru Core therefore records, per account: `SIGNED_IN_IDENTITY_ONLY`,
`INFERENCE_AUTHORIZED` (only after a provider-authorized call) and
`MODEL_TEST_PASSED` (only after a real successful test request).

## Matrix

| Provider | Official auth implemented in this repo | Identity vs inference | Entitlement / billing observed | Model test | Status |
| --- | --- | --- | --- | --- | --- |
| OpenAI (ChatGPT / OpenAI) | Sign in with ChatGPT (OIDC/OAuth + PKCE, dynamic client registration) and an independent OpenAI Platform API key | Identity-only consent never implies plan use, memory or history access | Plan usage vs Platform pay-as-you-go are distinct and must be observed | UNKNOWN | **Not connected** |
| Anthropic Claude | Console API key (or supported cloud-provider credentials). Optionally the owner's own unmodified official Claude Code client | Identity and inference are separate | Usage is observed from responses only | UNKNOWN | **Not connected** |
| Google Gemini / Vertex AI | Gemini Developer API key; **not offered**: consumer Google-login inference (Google ended individual Gemini Code Assist/Gemini CLI Google-login access for such use), token extraction, undocumented proxies | Google sign-in is identity only | Vertex needs authorized Cloud IAM/ADC and a project/region | UNKNOWN | **Not connected** |
| Z.ai GLM | Official API key | Identity separate from inference | Coding-plan compatibility must be verified before promising subscription login | UNKNOWN | **Not connected** |
| Kimi / Moonshot | Official API key | Identity separate from inference | Coding-plan compatibility must be verified before promising subscription login | UNKNOWN | **Not connected** |
| DeepSeek | Official API key | Identity separate from inference | Observed from responses only | UNKNOWN | **Not connected** |
| NVIDIA API Catalog / NIM | Official developer API key | Identity separate from inference | Enumerate only the models available to that key | UNKNOWN | **Not connected** |
| Grok / xAI | Official xAI API key; optional official Grok Build client handoff uses only documented methods | X sign-in is identity only and never enables Grok API, Premium/SuperGrok quota or external services | Observed from responses only | UNKNOWN | **Not connected** |
| Jan (local) | Direct OpenAI-compatible local API with an explicit allowlist | Not applicable (local) | No external billing | LIVE PASS on this machine for the owner's local model (A21) | **LIVE pilot passed** |

## What Boru Core *never* does

- No browser cookie or session extraction, no token copying from other apps,
  no undocumented or reverse-engineered endpoints, no provider-usage-limit
  bypass.
- No implicit inference entitlement from a sign-in, a repository connection, a
  Shell grant or a routing mode.
- No credential in configuration, logs, prompts, issues, CI artifacts,
  Langflow/Kandev exports or Shell output. Credentials are only ever referenced
  by an environment-variable name (see `boru/providers/cloud.py` and
  `boru/auth/tokens.py`).
- Automatic enrichment of entitlements after a fallback, a model change or a
  quota exhaustion.

## Connections contract (code)

- `boru/auth/` implements the official authorization-code + PKCE flow with a
  bounded loopback redirect capture, state/nonce verification and a token
  exchange that stores **only an opaque handle** (`TokenVault`, 0600 metadata
  file). No provider is connected by this repository.
- `boru/providers/cloud.py` is the HTTPS-enforced, allowlisted transport with
  an honest `configured` / `authenticated` connection state; it never claims an
  inference entitlement.
- Provider profiles must declare endpoint/region, model IDs, capability tags,
  auth method, quota evidence, credits (only when observable), budgets and
  connection status. Unknown usage is recorded as UNKNOWN, never invented.

## Secret-free example

~~~json
{
  "version": 1,
  "policy": {"optimization_mode": "AUTO", "inference_scope": "CLOUD_ALLOWED",
             "execution_profile": "LOCAL_ISOLATED", "disclosure_policy": "MINIMUM_NECESSARY"},
  "request_timeout": 60.0,
  "max_output_tokens": 256,
  "classifications": [{"boundary": "model_inference", "recipient": "cloud",
                        "data_class": "none"}],
  "providers": [
    {"kind": "cloud", "endpoint": "https://<provider-api-host>/v1",
     "api_key_env": "BORU_EXAMPLE_PROVIDER_KEY",
     "local_model_ids": ["example-model-id"], "allow_http": false}
  ]
}
~~~

`api_key_env` names an environment variable. Its value is read at request time
by the process only and is never written here.

## Running the connection (owner)

~~~bash
python3 -m boru connect --provider <name> \
  --authorization-endpoint https://<provider>/authorize \
  --token-endpoint https://<provider>/token \
  --client-id <registered-client-id> \
  [--client-secret-env <ENV_VAR>] \
  --redirect-uri http://127.0.0.1:8731/callback \
  --scope openid [--scope ...] \
  --vault-dir local-state/vault --timeout 300 [--no-browser]
python3 -m boru accounts --vault-dir local-state/vault
python3 -m boru disconnect --vault-dir local-state/vault --handle <handle>
~~~

The command prints the authorization URL (and opens the system browser unless
`--no-browser`), captures exactly one loopback redirect, verifies `state`,
exchanges the code with PKCE and stores **only an opaque handle**. The output
reports `connection_state: authenticated` with `model_test_passed: false` and
`identity_is_not_inference: true`: an identity is never an entitlement.
Registration with the provider is an owner action; this repository connects
nobody by itself. `TokenVault` persists handle metadata (owner-only, no secret
values) across restarts.

## What the owner does, step by step (Gate 2)

Registration is the owner's action; Boru Core connects nobody by itself. On the
provider's developer console, create an application and bring back these five
values (nothing else — no secret is committed, logged or stored by this
repository):

| Value | Example | Note |
| --- | --- | --- |
| Provider name | `openai` | used as the label in config and audit |
| Authorization endpoint | `https://provider.example/authorize` | must be `https` |
| Token endpoint | `https://provider.example/token` | must be `https`| Client ID | `app_1234...` | public identifier |
| Redirect URI | `http://127.0.0.1:8731/callback` | **numeric loopback**; a provider that refuses a plain-HTTP loopback redirect is a documented limitation, not a bypass to work around |
| Scopes | `openid email` | at most 16; the connection command requests them bound |

For a confidential client, the provider also issues a client secret: give Boru
only the **environment variable name** that holds it (`--client-secret-env`), and
set that variable in your own shell. Boru reads it at request time, never stores
it and never prints it.

Then run the command above (`--vault-dir` must be an existing owner-only
directory). The result is either an opaque handle in the vault — an identity,
`model_test_passed: false`, `identity_is_not_inference: true` — or a typed
refusal. A successful sign-in is **not** inference authorization and never
widens a policy axis.

## Status

**DESIGNED / PILOTABLE.** No provider account is connected by this repository
and no cloud inference has occurred; the local Jan pilot (A21) is the only live
inference evidence. The connection flow above is implemented and tested against
a test-owned provider; running it against a real provider is an owner action
requiring a registered client.
