"""Deterministic state machine tests."""
import unittest

from boru.errors import InvalidTransition
from boru.state import TaskState, TaskRecord, can_transition, utc_now
from boru.types import TaskEnvelope


def record(task_id: str = "t1") -> TaskRecord:
    return TaskRecord(task_id=task_id, envelope=TaskEnvelope(task_id=task_id, goal="g"))


class TransitionTests(unittest.TestCase):
    def test_happy_path(self):
        item = record()
        for target in (TaskState.CLASSIFIED, TaskState.PLANNED, TaskState.QUEUED,
                       TaskState.RUNNING, TaskState.VERIFYING, TaskState.REVIEW):
            item.transition(target, "test", "2026-01-01T00:00:00Z")
        self.assertEqual(TaskState.REVIEW, item.state)

    def test_terminal_states_reject_further_moves(self):
        for terminal in (TaskState.DONE, TaskState.FAILED, TaskState.CANCELLED):
            item = record()
            item.state = terminal
            with self.assertRaises(InvalidTransition):
                item.transition(TaskState.RUNNING, "test", "2026-01-01T00:00:00Z")
            self.assertFalse(can_transition(terminal, TaskState.RUNNING))

    def test_invalid_jump_rejected(self):
        item = record()
        with self.assertRaises(InvalidTransition):
            item.transition(TaskState.DONE, "test", "2026-01-01T00:00:00Z")
        with self.assertRaises(InvalidTransition):
            item.transition(TaskState.RUNNING, "test", "2026-01-01T00:00:00Z")

    def test_hold_is_resumable_and_cancellable(self):
        item = record()
        item.transition(TaskState.HOLD, "hold", "2026-01-01T00:00:00Z")
        self.assertTrue(item.can_transition_to(TaskState.QUEUED))
        item.transition(TaskState.QUEUED, "resume", "2026-01-01T00:00:00Z")
        self.assertTrue(item.can_transition_to(TaskState.CANCELLED))

    def test_same_state_transition_is_idempotent(self):
        item = record()
        before = len(item.events)
        item.transition(TaskState.CREATED, "again", "2026-01-01T00:00:00Z")
        self.assertEqual(before, len(item.events))

    def test_event_audit_trail_records_transitions(self):
        item = record()
        item.transition(TaskState.CLASSIFIED, "classified", "2026-01-01T00:00:00Z")
        self.assertEqual(1, len(item.events))
        self.assertEqual(("CREATED", "CLASSIFIED", "classified"), tuple(item.events[0][k] for k in ("from", "to", "reason")))

    def test_utc_now_format(self):
        stamp = utc_now()
        self.assertTrue(stamp.endswith("+00:00") or stamp.endswith("Z"))


if __name__ == "__main__":
    unittest.main()
