"""Budget, cooldown and compaction tests (P3)."""
import unittest

from boru.budgets import (
    MAX_RESERVATIONS,
    Budget,
    BudgetLedger,
    CooldownTracker,
    compact,
    estimate_message_tokens,
    estimate_tokens,
)
from boru.errors import PolicyViolation
from boru.providers.base import ChatMessage


def messages(count=6):
    out = [ChatMessage("system", "rules and invariants")]
    for index in range(count):
        out.append(ChatMessage("user" if index % 2 == 0 else "assistant", "turn-{}:{}".format(index, "x" * 40)))
    return out


class BudgetTests(unittest.TestCase):
    def test_validation(self):
        self.assertEqual([], Budget(max_input_tokens=10, max_output_tokens=5, max_total_tokens=20).validate())
        for bad in (dict(max_input_tokens=0), dict(max_input_tokens=True),
                    dict(max_total_tokens=1, max_input_tokens=10), dict(max_cost_usd=0),
                    dict(max_cost_usd=float("nan")), dict(max_cost_usd="5")):
            with self.assertRaises(PolicyViolation):
                Budget(**bad).assert_valid()

    def test_estimator_is_deterministic_and_bounded(self):
        self.assertEqual(1, estimate_tokens(""))
        self.assertEqual(estimate_tokens("abcd"), estimate_tokens("abcd"))
        self.assertEqual(4 + 1, estimate_message_tokens([ChatMessage("user", "abcd")]))

    def test_reservation_refuses_projections_over_the_ceiling(self):
        ledger = BudgetLedger(ceiling=Budget(max_total_tokens=100))
        self.assertEqual((True, ""), ledger.reserve("t1", estimated_input=10, requested_output=20))
        self.assertEqual((False, "estimated_total_over_ceiling"),
                         ledger.reserve("t2", estimated_input=90, requested_output=20))
        self.assertEqual((False, "estimated_input_over_ceiling"),
                         ledger.reserve("t3", estimated_input=90, requested_output=5,
                                        ceiling=Budget(max_input_tokens=10)))

    def test_observed_usage_is_rechecked(self):
        ledger = BudgetLedger(ceiling=Budget(max_total_tokens=100, max_cost_usd=1.0))
        self.assertTrue(ledger.reserve("t1", estimated_input=1, requested_output=1)[0])
        self.assertTrue(ledger.record("t1", {"input_tokens": 2, "output_tokens": 3, "total_tokens": 5})[0])
        self.assertEqual((False, "observed_total_over_ceiling"),
                         ledger.record("t1", {"total_tokens": 999}))
        self.assertTrue(ledger.record("t1", None, cost_usd=0.5)[0])
        self.assertEqual((False, "cost_over_ceiling"), ledger.record("t1", None, cost_usd=9.0))

    def test_partial_usage_is_summed(self):
        ledger = BudgetLedger(ceiling=Budget(max_total_tokens=10))
        ledger.reserve("t1", estimated_input=1, requested_output=1)
        self.assertTrue(ledger.record("t1", {"input_tokens": 4, "output_tokens": 3})[0])
        self.assertEqual(7, ledger.observed("t1")["observed_total"])

    def test_bad_inputs_rejected(self):
        ledger = BudgetLedger(ceiling=Budget(max_total_tokens=100))
        for bad in (dict(estimated_input=-1, requested_output=1), dict(estimated_input=1, requested_output=0),
                    dict(estimated_input="1", requested_output=1)):
            with self.assertRaises(PolicyViolation):
                ledger.reserve("t1", **bad)
        with self.assertRaises(PolicyViolation):
            ledger.reserve("", estimated_input=1, requested_output=1)
        ledger.reserve("t2", estimated_input=1, requested_output=1)
        with self.assertRaises(PolicyViolation):
            ledger.record("unknown", {"total_tokens": 1})
        with self.assertRaises(PolicyViolation):
            ledger.record("t2", {"total_tokens": -3})
        with self.assertRaises(PolicyViolation):
            ledger.record("t2", None, cost_usd=float("inf"))


class CooldownTests(unittest.TestCase):
    def test_cooldown_lifetimes(self):
        tracker = CooldownTracker(seconds=30)
        tracker.cool("mock", "m1", now=1000)
        self.assertFalse(tracker.available("mock", "m1", now=1010))
        self.assertTrue(tracker.available("mock", "m1", now=1031))
        self.assertTrue(tracker.available("mock", "m2", now=1005))
        self.assertEqual([("mock", "m1")], tracker.active(now=1005))
        self.assertEqual([], tracker.active(now=2000))

    def test_bad_inputs_rejected(self):
        for bad in (0, True, "30", 9999):
            with self.assertRaises(PolicyViolation):
                CooldownTracker(seconds=bad)
        tracker = CooldownTracker(seconds=30)
        with self.assertRaises(PolicyViolation):
            tracker.cool("mock", "m", seconds=0)


class CompactionTests(unittest.TestCase):
    def test_bound_is_enforced_and_reported(self):
        result = compact(messages(), max_chars=256, keep_last=2)
        self.assertTrue(result.dropped_turns >= 1)
        self.assertLessEqual(sum(len(m.content) for m in result.messages), 256)
        self.assertEqual("heuristic_bound_not_semantic", result.note)
        self.assertTrue(any(m.role == "system" for m in result.messages))

    def test_short_conversations_are_unchanged(self):
        short = [ChatMessage("user", "hello")]
        result = compact(short, max_chars=256)
        self.assertEqual(0, result.dropped_turns)
        self.assertEqual(1, len(result.messages))
        self.assertEqual(estimate_message_tokens(short), result.estimated_input_tokens)

    def test_bounds_are_validated(self):
        for bad in (10, True, "256", 1 << 21):
            with self.assertRaises(PolicyViolation):
                compact(messages(), max_chars=bad)
        with self.assertRaises(PolicyViolation):
            compact(messages(), max_chars=256, keep_last=0)

    def test_compaction_never_reaches_the_ceiling(self):
        result = compact(messages(20), max_chars=512, keep_last=2)
        self.assertTrue(sum(len(m.content) for m in result.messages) <= 512)


class ReservationBoundTests(unittest.TestCase):
    """Reservations are bounded and released at the end of a task's life."""

    def test_reservations_stay_bounded(self):
        ledger = BudgetLedger()
        for index in range(MAX_RESERVATIONS + 16):
            ledger.reserve("t{}".format(index), estimated_input=10, requested_output=8)
        self.assertLessEqual(len(ledger._reserved), MAX_RESERVATIONS)

    def test_release_is_idempotent_and_a_stale_reservation_refuses(self):
        from boru.errors import PolicyViolation

        ledger = BudgetLedger()
        ledger.reserve("t1", estimated_input=1, requested_output=1)
        ledger.release("t1")
        ledger.release("t1")  # idempotent
        with self.assertRaises(PolicyViolation):
            ledger.record("t1", {"input_tokens": 1, "output_tokens": 1})
        with self.assertRaises(PolicyViolation):
            ledger.observed("t1")

    def test_a_reviewed_task_releases_its_reservation(self):
        from boru.config import CoreConfig, ProviderConfig
        from boru.core import BoruCore
        from boru.types import TaskEnvelope

        engine = BoruCore(CoreConfig(providers=(ProviderConfig(kind="mock"),)))
        try:
            engine.submit(TaskEnvelope(task_id="t1", goal="g"))
            engine.dispatch_next()
            self.assertIn("t1", engine.budgets._reserved)
            engine.review("t1", accept=True)
            self.assertNotIn("t1", engine.budgets._reserved)
        finally:
            engine.close()


if __name__ == "__main__":
    unittest.main()
