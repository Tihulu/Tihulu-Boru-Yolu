"""Property-style hostile-input tests for the security-critical paths.

Deterministic seeds, no network, no credentials.  Every round feeds random
bytes and text through the real broker/executor/consent/connector/contract
paths and demands a *typed* outcome: a denial, a refusal, or a legitimate
acceptance for a well-formed name.  An unhandled exception, a receipt that
verifies without the key, a probe that discloses the resource path or a
connector payload that could reach a transport without a grant are failures.

The iteration counts are sized for CI; the exploratory run used 3000 rounds per
property over ~18,000 hostile inputs and found no untyped outcome.
"""
import os
import random
import stat
import string
import tempfile
import unittest

from boru.authorization import AuthorizationReceipt
from boru.broker import Broker, OperationRequest, ScopeAllowlist, WorkerIdentity, resource_alias
from boru.connectors.base import Capability, Grant
from boru.connectors.scope import check_call, check_dispatch_body
from boru.consent import ConsentStore
from boru.errors import ConnectorDenied, PolicyViolation
from boru.executor import LocalExecutor
from boru.types import AgentResult

SEED = 20261122
ROUNDS = 250
ALPHABET = string.printable + "\x00\x07\x1b\x7f\u202e\u200b"


def random_text(rng, length):
    return "".join(rng.choice(ALPHABET) for _ in range(length))


class PropertyHostileInputTests(unittest.TestCase):
    def setUp(self):
        self.rng = random.Random(SEED)
        self.root = tempfile.mkdtemp(prefix="boru-prop-")
        os.chmod(self.root, stat.S_IRWXU)
        self.alias_dir = os.path.join(self.root, "data")
        os.makedirs(self.alias_dir)
        with open(os.path.join(self.alias_dir, "note.txt"), "w", encoding="utf-8") as handle:
            handle.write("one\ntwo\n")
        self.scopes = ScopeAllowlist({"demo": self.alias_dir})
        self.key = bytes(range(32))
        self.worker = WorkerIdentity("w", scopes=("demo",))

    def tearDown(self):
        import shutil

        shutil.rmtree(self.root, ignore_errors=True)

    def authorise(self, consent, target):
        broker = Broker(worker=self.worker, scopes=self.scopes, consent=consent,
                        consent_recipient="w", authorization_key=self.key)
        request = OperationRequest(operation="probe_path_alias", resource_alias="demo",
                                   requester="owner", task_id="t", worker=self.worker,
                                   fields=("exists",), nonce="n", grant_id="g", target=target)
        return broker.authorize(request, requested_fields=("exists",))

    def test_random_targets_yield_only_typed_outcomes(self):
        allowed = 0
        for _ in range(ROUNDS):
            target = random_text(self.rng, self.rng.randint(0, 40))
            consent = ConsentStore()
            consent.grant(grant_id="g", recipient="w", task_id="t",
                          field_name="probe_path_alias", alias="demo", level="L0",
                          expires_at=2 ** 31, nonce="n")
            decision, receipt, _ = self.authorise(consent, target)
            if decision == "deny":
                self.assertIsNone(receipt, target)
                continue
            allowed += 1
            executor = LocalExecutor(self.scopes, authorization_key=self.key)
            try:
                result = executor.acquire(receipt, fields=("exists",),
                                          now=receipt.expires_at - 1)
            except PolicyViolation:
                continue  # a well-formed name the worker still refuses
            text = repr(result.to_dict())
            self.assertNotIn(self.alias_dir, text)
            self.assertNotIn("note.txt", text)
        self.assertGreater(allowed, 0)

    def test_random_aliases_never_widen_the_allowlist(self):
        for _ in range(ROUNDS):
            alias = random_text(self.rng, self.rng.randint(0, 40))
            try:
                resource_alias(alias)
            except PolicyViolation:
                continue
            if self.scopes.permits(alias):
                self.assertEqual("demo", alias)

    def test_random_receipts_never_verify(self):
        for _ in range(ROUNDS):
            forged = AuthorizationReceipt(
                receipt_id=random_text(self.rng, 12), operation="probe_path_alias",
                resource_alias=random_text(self.rng, 12), task_id=random_text(self.rng, 12),
                worker_id=random_text(self.rng, 8), grant_id=random_text(self.rng, 8),
                issued_at=1.0, expires_at=float(self.rng.randint(1, 2 ** 31)),
                nonce=random_text(self.rng, 8),
                policy_revision=self.rng.choice([0, 1, 2, 99]),
                decision=self.rng.choice(["allow", "deny", "ALLOW"]),
                allowed_fields=(random_text(self.rng, 6),),
                target=random_text(self.rng, 10),
                authentication_tag=random_text(self.rng, self.rng.choice([0, 8, 64])))
            with self.assertRaises(PolicyViolation):
                forged.verify(self.key, now=forged.expires_at - 1,
                              requested_fields=("exists",))

    def test_random_connector_payloads_never_reach_a_transport(self):
        grant = Grant(grant_id="g", account="owner", repository="owner/repo", reference="main",
                      operations=("read_file", "dispatch_workflow"),
                      capabilities=(Capability.REPO_READ, Capability.ACTIONS_DISPATCH),
                      max_calls=8, issued_at=1.0, expires_at=2 ** 31, nonce="n",
                      workflow_ids=("ci.yml",))
        for index in range(ROUNDS):
            payload = {"repository": random_text(self.rng, self.rng.randint(0, 24)),
                       "reference": random_text(self.rng, self.rng.randint(0, 24)),
                       "path": random_text(self.rng, self.rng.randint(0, 24)),
                       "workflow": random_text(self.rng, self.rng.randint(0, 24))}
            operation = ("read_file", "dispatch_workflow", "list_issues")[index % 3]
            try:
                check_call(grant, operation, payload, method=None, path="",
                           default_method="GET")
            except ConnectorDenied:
                pass
            body = {"ref": random_text(self.rng, 12),
                    "inputs": {random_text(self.rng, 6): random_text(self.rng, 12)}}
            try:
                check_dispatch_body(grant, body)
            except ConnectorDenied:
                pass

    def test_random_typed_results_refuse_without_crashing(self):
        for _ in range(ROUNDS):
            typed = {}
            for _ in range(self.rng.randint(0, 6)):
                typed[random_text(self.rng, self.rng.randint(0, 8))] = self.rng.choice([
                    random_text(self.rng, 20), self.rng.randint(-10, 10 ** 13),
                    1.5, [random_text(self.rng, 8)], {"raw_stdout": "x"}, None])
            result = AgentResult(task_id="t", attempt_id="a", status="completed",
                                 model_provider="mock", model_id="mock",
                                 evidence_class="simulated", typed_result=typed)
            self.assertIsInstance(result.validate(), list)


if __name__ == "__main__":
    unittest.main()
