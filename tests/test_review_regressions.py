"""Independent security regression probes for TIHULU Boru Yolu (Gate 1).

Originally supplied by the external security reviewer for cc73940; kept in the
repository so CI runs the same executable acceptance spec on every change.

Run after a local clone, from its root, without host installation or network:
    PYTHONPATH=. python3 /path/to/boru_security_regressions_cc73940.py -v

Each test expresses the desired SECURITY behaviour; failures identify defects.
No real credentials, model calls, sandbox runtime or external connections.
This suite has NOT been executed against the repo in the review environment.
"""
import os
import tempfile
import time
import unittest
from pathlib import Path

from boru.audit import RejectionLedger
from boru.broker import Broker, OperationRequest, ScopeAllowlist, WorkerIdentity
from boru.consent import ConsentStore as PersistentConsent
from boru.connectors.base import Capability, Grant
from boru.connectors.github import GitHubProvider
from boru.connectors.gitlab import GitLabProvider
from boru.connectors.polling import EventAllowlist, PollingSync, SyncEvent
from boru.connectors.scope import RepositoryRef
from boru.errors import ConnectorDenied, PolicyViolation
from boru.privacy import (ConsentStore as LocalConsent, DisclosureGate,
                          DisclosureRequest, GateDecision)
from boru.types import AgentResult, TaskEnvelope
from boru.workers import WorkerRegistry


def grant(*, operation, reference="main", capability=Capability.REPO_READ,
          workflow_ids=(), account="owner"):
    return Grant(grant_id="test-g", account=account, repository="owner/repo",
                 reference=reference, operations=(operation,),
                 capabilities=(capability,), max_calls=8,
                 issued_at=time.time(), expires_at=time.time()+60,
                 nonce="test-n", workflow_ids=workflow_ids)


class SecurityRegressions(unittest.TestCase):
    def test_l0_owner_grant_cannot_authorize_l2_local(self):
        consent = LocalConsent()
        consent.grant(grant_id="g", recipient="cloud", task_id="t", field_name="excerpt",
                      level="L0", expires_at=time.time()+60, nonce="n")
        request = DisclosureRequest(task_id="t", recipient="cloud", level="L2",
                                    fields=("excerpt",),
                                    payload={"excerpt":"SYNTHETIC_PRIVATE_TEXT", "grant_id":"g", "nonce":"n"})
        decision, released, _ = DisclosureGate("SCOPED_APPROVED").release(request, consent)
        self.assertEqual(GateDecision.DENY, decision)
        self.assertEqual({}, released)

    def test_l0_owner_grant_cannot_authorize_l2_persistent(self):
        with PersistentConsent() as consent:
            consent.grant(grant_id="g", recipient="cloud", task_id="t", field_name="excerpt",
                          level="L0", expires_at=time.time()+60, nonce="n")
            request = DisclosureRequest(task_id="t", recipient="cloud", level="L2",
                                        fields=("excerpt",),
                                        payload={"excerpt":"SYNTHETIC_PRIVATE_TEXT", "grant_id":"g", "nonce":"n"})
            decision, released, _ = DisclosureGate("SCOPED_APPROVED").release(request, consent)
            self.assertEqual(GateDecision.DENY, decision)
            self.assertEqual({}, released)

    def test_broker_rejects_attacker_supplied_worker_scope(self):
        with tempfile.TemporaryDirectory() as directory:
            a, b = Path(directory)/"a", Path(directory)/"b"
            a.mkdir(); b.mkdir()
            consent = PersistentConsent()
            try:
                consent.grant(grant_id="g", recipient="local-worker", task_id="t",
                              field_name="list_dir_alias", level="L0",
                              expires_at=time.time()+60, nonce="n")
                broker = Broker(worker=WorkerIdentity("w", scopes=("A",)),
                                scopes=ScopeAllowlist({"A":str(a), "B":str(b)}),
                                consent=consent)
                request = OperationRequest(operation="list_dir_alias", resource_alias="B",
                                           requester="owner", task_id="t",
                                           worker=WorkerIdentity("w", scopes=("B",)),
                                           fields=("entry_count",), nonce="n", grant_id="g")
                decision, _, _ = broker.authorize(request)
                self.assertEqual("deny", decision)
            finally:
                consent.close()

    def test_intermediate_symlink_alias_is_denied(self):
        with tempfile.TemporaryDirectory() as directory:
            safe, outside = Path(directory)/"safe", Path(directory)/"outside"
            safe.mkdir(); (outside/"target").mkdir(parents=True)
            (outside/"target"/"outside-marker.txt").write_text("synthetic")
            (safe/"bridge").symlink_to(outside, target_is_directory=True)
            scope = ScopeAllowlist({"demo":str(safe/"bridge"/"target")})
            self.assertTrue(scope.validate(), "Intermediate symlink must be refused")

    def test_worker_registry_cannot_issue_nonfinite_expiry(self):
        registry = WorkerRegistry()
        registry.create("w", ("demo",), now=float("nan"))
        self.assertFalse(registry.valid("w", registry.secret_for("w")))

    def test_ledger_rejects_private_path_as_subject(self):
        with RejectionLedger() as ledger:
            private = "/home/EXAMPLE/.ssh/id_ed25519"
            ledger.record("broker", private, "denied", "operation")
            self.assertNotIn(private, repr(ledger.recent()))

    def test_github_read_file_must_use_granted_reference(self):
        requests = []
        provider = GitHubProvider(transport=lambda method, path, body:
                                  requests.append((method, path, body)) or (200,b'{}'))
        provider.call(grant(operation="read_file", reference="feature"), "read_file",
                      {"repository":"owner/repo","reference":"feature","path":"docs/x.md"})
        self.assertIn("?ref=feature", requests[0][1])

    def test_gitlab_read_file_must_use_granted_reference(self):
        requests = []
        provider = GitLabProvider(transport=lambda method, path, body:
                                  requests.append((method, path, body)) or (200,b'{}'))
        provider.call(grant(operation="read_file", reference="feature"), "read_file",
                      {"repository":"owner/repo","reference":"feature","path":"docs/x.md"})
        self.assertIn("?ref=feature", requests[0][1])

    def test_workflow_rerun_cannot_ignore_workflow_allowlist(self):
        requests = []
        provider = GitHubProvider(transport=lambda method, path, body:
                                  requests.append((method, path)) or (201,b'{}'))
        approved = grant(operation="rerun_workflow", capability=Capability.ACTIONS_DISPATCH,
                         workflow_ids=("approved.yml",))
        with self.assertRaises(ConnectorDenied):
            provider.call(approved, "rerun_workflow", {"repository":"owner/repo",
                          "reference":"main", "run_id":"999999"})
        self.assertEqual([], requests)

    def test_workflow_dispatch_cannot_override_reference_in_body(self):
        requests = []
        provider = GitHubProvider(transport=lambda method, path, body:
                                  requests.append((method, path, body)) or (204,b''))
        with self.assertRaises(ConnectorDenied):
            provider.call(grant(operation="dispatch_workflow", capability=Capability.ACTIONS_DISPATCH,
                                workflow_ids=("ci.yml",)), "dispatch_workflow",
                          {"repository":"owner/repo", "reference":"main", "workflow":"ci.yml"},
                          body={"ref":"ungranted-branch","inputs":{"unknown":"synthetic"}})
        self.assertEqual([], requests)

    def test_github_call_must_enforce_account_identity(self):
        requests = []
        old = os.environ.get("BORU_REVIEW_SYNTHETIC_TOKEN")
        os.environ["BORU_REVIEW_SYNTHETIC_TOKEN"] = "synthetic-not-real"
        try:
            def transport(method, path, body):
                requests.append(path)
                if path == "/user": return 200,b'{"login":"intruder"}'
                return 200,b'{}'
            provider = GitHubProvider(token_env="BORU_REVIEW_SYNTHETIC_TOKEN", transport=transport)
            with self.assertRaises(ConnectorDenied):
                provider.call(grant(operation="list_issues", account="owner"),
                              "list_issues", {"repository":"owner/repo", "reference":"main"})
            self.assertNotIn("/repos/owner/repo/issues", requests)
        finally:
            if old is None: os.environ.pop("BORU_REVIEW_SYNTHETIC_TOKEN",None)
            else: os.environ["BORU_REVIEW_SYNTHETIC_TOKEN"] = old

    def test_connector_audit_does_not_record_repository_paths(self):
        provider = GitHubProvider(transport=lambda *_: (200,b'{}'))
        provider.call(grant(operation="list_issues"), "list_issues",
                      {"repository":"owner/repo","reference":"main"})
        self.assertNotIn("/repos/", repr(provider.audit()))

    def test_result_contract_denies_nested_raw_host_content(self):
        result = AgentResult(task_id="t",attempt_id="a",status="completed",
                             model_provider="mock",model_id="mock-text-v1",
                             evidence_class="simulated",
                             typed_result={"text":{"raw_stdout":"SYNTHETIC_PRIVATE_TEXT"}})
        self.assertTrue(result.validate(),"Nested raw_stdout must not validate")

    def test_polling_does_not_replay_evicted_event_ids(self):
        sync = PollingSync(EventAllowlist(("push",)))
        sync.accept([SyncEvent(event_id=f"e{i}",event_type="push") for i in range(4097)])
        self.assertEqual([],sync.normalize([{"id":"e0", "type":"push", "payload":{}}]))

    def test_grant_revocation_cannot_be_erased_by_same_id_reissue(self):
        with PersistentConsent() as store:
            store.grant(grant_id="g", recipient="cloud", task_id="t", field_name="excerpt",
                        level="L2", expires_at=time.time()+60, nonce="n1")
            store.revoke("g")
            with self.assertRaises((ValueError, RuntimeError)):
                store.grant(grant_id="g",recipient="cloud",task_id="t",field_name="excerpt",
                            level="L2",expires_at=time.time()+60,nonce="n2")

    def test_mock_provider_cannot_claim_direct_evidence(self):
        from boru.config import CoreConfig, ProviderConfig
        from boru.core import BoruCore
        from boru.providers.base import ChatReply
        core = BoruCore(CoreConfig(providers=(ProviderConfig(kind="mock"),)))
        try:
            core.submit(TaskEnvelope(task_id="mock-direct", goal="synthetic"))
            provider = core._providers["mock"]
            provider.chat = lambda model_id, messages, **kw: ChatReply(
                provider="mock", model_id=model_id, request_id="synthetic-request",
                content="synthetic", evidence_class="direct")
            summary = core.dispatch_next()
            self.assertNotEqual("direct", summary["evidence_class"])
        finally:
            core.close()

    def test_worker_id_must_not_escape_registry_directory(self):
        from boru.errors import ConfigurationError
        with tempfile.TemporaryDirectory(prefix="boru-registry-escape-") as base:
            workers = Path(base) / "workers"
            workers.mkdir(mode=0o700)
            (workers / "worker-x").mkdir(mode=0o700)
            victim = Path(base) / "outside.json"
            victim.write_text("SYNTHETIC_KEEP_ME")
            registry = WorkerRegistry(str(workers))
            with self.assertRaises(ConfigurationError):
                registry.create("x/../../outside", ("demo",))
            self.assertEqual("SYNTHETIC_KEEP_ME", victim.read_text())

    def test_receipt_must_never_disclose_absolute_alias_path(self):
        with tempfile.TemporaryDirectory(prefix="boru-receipt-path-") as root:
            with PersistentConsent() as consent:
                consent.grant(grant_id="g", recipient="local-worker", task_id="t",
                              field_name="probe_path_alias", level="L0",
                              expires_at=time.time()+60, nonce="n")
                worker = WorkerIdentity("w", scopes=(root,))
                broker = Broker(worker=worker, scopes=ScopeAllowlist({root:root}),
                                consent=consent)
                request = OperationRequest(operation="probe_path_alias", resource_alias=root,
                                           requester="owner", task_id="t", worker=worker,
                                           fields=("exists",), nonce="n", grant_id="g")
                decision, receipt, _ = broker.authorize(request)
                self.assertEqual("allow", decision)
                self.assertNotIn(root, repr(receipt))

    def test_executor_rejects_unsigned_or_denied_receipt(self):
        from boru.broker import AuthorizationReceipt
        from boru.executor import LocalExecutor
        with tempfile.TemporaryDirectory(prefix="boru-forged-receipt-") as root:
            now = time.time()
            receipt = AuthorizationReceipt(
                receipt_id="br-forged", operation="list_dir_alias", resource_alias="demo",
                task_id="t-forged", worker_id="unauthenticated", grant_id="absent",
                issued_at=now, expires_at=now + 60, nonce="n-forged",
                policy_revision=1, decision="deny")
            executor = LocalExecutor(ScopeAllowlist({"demo": root}))
            with self.assertRaises(PolicyViolation):
                executor.acquire(receipt, fields=("entry_count",), now=now + 1)

    def test_repository_slots_reject_nul(self):
        with self.assertRaises(ConnectorDenied):
            RepositoryRef.parse("owner/repo\x00extra")


if __name__ == "__main__":
    unittest.main()
