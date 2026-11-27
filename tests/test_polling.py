"""Localhost polling sync tests (issue #8): allowlist, idempotency, no listener."""
import unittest

from boru.connectors.polling import EventAllowlist, PollingSync, SyncEvent, MAX_SEEN
from boru.errors import ConnectorDenied


def raw(events):
    return list(events)


class AllowlistTests(unittest.TestCase):
    def test_only_declared_types_pass(self):
        allow = EventAllowlist(("issues", "push"))
        self.assertTrue(allow.permits("issues"))
        self.assertFalse(allow.permits("delete"))

    def test_bad_allowlists_refused(self):
        for bad in ([], ("a", "a"), ("",), ("x" * 200,), "issues"):
            with self.assertRaises(ConnectorDenied):
                EventAllowlist(bad)


class SyncTests(unittest.TestCase):
    def setUp(self):
        self.sync = PollingSync(EventAllowlist(("issues", "push")))

    def test_new_events_are_accepted_once(self):
        events = self.sync.normalize(raw([
            {"id": "e1", "type": "issues", "payload": {"number": 1}},
            {"id": "e2", "type": "push", "payload": {}},
        ]))
        accepted = self.sync.accept(events)
        self.assertEqual(["e1", "e2"], [e.event_id for e in accepted])
        # a second sync of the same payload is idempotent: no rework
        self.assertEqual([], self.sync.accept(self.sync.normalize(raw([
            {"id": "e1", "type": "issues", "payload": {"number": 1}},
        ]))))

    def test_event_seen_survives_a_restart(self):
        events = self.sync.normalize(raw([{"id": "e9", "type": "push", "payload": {}}]))
        self.sync.accept(events)
        restarted = PollingSync(EventAllowlist(("push",)), seen=self.sync.seen)
        self.assertEqual([], restarted.accept(restarted.normalize(raw([
            {"id": "e9", "type": "push", "payload": {}}]))))

    def test_undeclared_type_is_refused(self):
        with self.assertRaises(ConnectorDenied) as raised:
            self.sync.normalize(raw([{"id": "e1", "type": "delete_repo", "payload": {}}]))
        self.assertEqual("event_type_not_allowed", str(raised.exception))

    def test_malformed_events_are_refused(self):
        for bad in ("nope", {"id": "e"}, [{"id": "e1", "type": "push", "extra": 1}],
                    [{"id": "", "type": "push"}], [{"id": "e1", "type": "push",
                                                   "payload": {"k{}".format(i): 1 for i in range(40)}}]):
            with self.assertRaises(ConnectorDenied):
                self.sync.normalize(bad)

    def test_history_never_forgets_an_evicted_id(self):
        # Test that a full registry refuses new ids instead of forgetting old ones
        # Pre-fill registry to MAX_SEEN
        seen = ["e{}".format(i) for i in range(MAX_SEEN)]
        full_sync = PollingSync(EventAllowlist(("push",)), seen=seen)
        self.assertEqual(MAX_SEEN, len(full_sync.seen))
        # New events should be refused
        with self.assertRaises(ConnectorDenied) as ctx:
            full_sync.accept([SyncEvent(event_id="new", event_type="push", payload={})])
        self.assertEqual("seen_registry_exhausted", str(ctx.exception))
        # Original ids must still be in registry (not forgotten)
        self.assertIn("e0", full_sync.seen)
        self.assertIn("e{}".format(MAX_SEEN - 1), full_sync.seen)

    def test_non_string_raw_id_refused_before_coercion(self):
        """Integer, dict, None raw IDs must be refused, not silently coerced."""
        for bad_id in [123, {"nested": "bad"}, None, 0.5, b"bytes"]:
            with self.assertRaises(ConnectorDenied) as ctx:
                self.sync.normalize(raw([{"id": bad_id, "type": "issues", "payload": {}}]))
            self.assertEqual("event_id_malformed", str(ctx.exception))

    def test_empty_and_whitespace_raw_id_refused(self):
        for bad_id in ["", "  ", "\t", "\n"]:
            with self.assertRaises(ConnectorDenied):
                self.sync.normalize(raw([{"id": bad_id, "type": "issues", "payload": {}}]))

    def test_non_string_raw_type_refused(self):
        for bad_type in [123, None, [], {"a": 1}]:
            with self.assertRaises(ConnectorDenied):
                self.sync.normalize(raw([{"id": "e1", "type": bad_type, "payload": {}}]))

    def test_accept_rejects_malformed_sync_event_no_mutation(self):
        """accept() must not mutate seen when a crafted SyncEvent has a bad ID."""
        self.sync.accept([SyncEvent(event_id="good", event_type="issues", payload={})])
        seen_before = len(self.sync.seen)
        with self.assertRaises(ConnectorDenied):
            self.sync.accept([SyncEvent(event_id=12345, event_type="issues", payload={})])  # type: ignore
        seen_after = len(self.sync.seen)
        self.assertEqual(seen_before, seen_after, "accept() partially mutated seen on bad event")

    def test_accept_rejects_disallowed_event_type_no_mutation(self):
        """accept() must not mutate seen when event type is not on allowlist."""
        self.sync.accept([SyncEvent(event_id="e2", event_type="issues", payload={})])
        seen_before = len(self.sync.seen)
        with self.assertRaises(ConnectorDenied):
            self.sync.accept([SyncEvent(event_id="e3", event_type="delete", payload={})])
        seen_after = len(self.sync.seen)
        self.assertEqual(seen_before, seen_after, "accept() partially mutated seen on disallowed type")

    def test_batch_partial_rejection_does_not_mutate_seen(self):
        """If any event in a batch fails validation, the entire batch is rejected."""
        self.sync.accept([SyncEvent(event_id="b1", event_type="issues", payload={})])
        seen_before = len(self.sync.seen)
        with self.assertRaises(ConnectorDenied):
            self.sync.accept([
                SyncEvent(event_id="b2", event_type="issues", payload={}),
                SyncEvent(event_id="", event_type="issues", payload={}),
            ])
        seen_after = len(self.sync.seen)
        self.assertEqual(seen_before, seen_after, "batch rejection partially mutated seen")

    def test_no_listener_is_created(self):
        # the module imports no socket, server or threading primitives
        import boru.connectors.polling as module

        source = open(module.__file__, "r", encoding="utf-8").read()
        for forbidden in ("socket", "ThreadingHTTPServer", "BaseHTTPRequestHandler"):
            self.assertNotIn(forbidden, source, forbidden)


if __name__ == "__main__":
    unittest.main()
