"""Localhost polling sync tests (issue #8): allowlist, idempotency, no listener."""
import unittest

from boru.connectors.polling import EventAllowlist, PollingSync, SyncEvent
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
        events = [SyncEvent(event_id="e{}".format(i), event_type="push")
                  for i in range(5000)]
        self.sync.accept(events)
        self.assertEqual(5000, len(self.sync.seen))
        # an evicted id is never replayed, and a full registry refuses new
        # work instead of forgetting an old id
        self.assertEqual([], self.sync.accept(self.sync.normalize(
            raw([{"id": "e0", "type": "push", "payload": {}}]))))
        with self.assertRaises(ConnectorDenied):
            self.sync.accept([SyncEvent(event_id="e{}".format(i), event_type="push")
                              for i in range(5000, 5000 + 4000)])

    def test_no_listener_is_created(self):
        # the module imports no socket, server or threading primitives
        import boru.connectors.polling as module

        source = open(module.__file__, "r", encoding="utf-8").read()
        for forbidden in ("socket", "ThreadingHTTPServer", "BaseHTTPRequestHandler", "threading"):
            self.assertNotIn(forbidden, source, forbidden)


if __name__ == "__main__":
    unittest.main()
