"""Bounded queue and idempotency tests."""
import unittest

from boru.errors import DuplicateTask, QueueFull
from boru.queue import BoundedTaskQueue
from boru.types import TaskEnvelope


def envelope(task_id: str, key: str = None) -> TaskEnvelope:
    return TaskEnvelope(task_id=task_id, goal="g", idempotency_key=key or task_id)


class QueueTests(unittest.TestCase):
    def test_fifo_and_bounds(self):
        queue = BoundedTaskQueue(maxsize=2)
        queue.put(envelope("a"))
        queue.put(envelope("b"))
        self.assertEqual(["a", "b"], [e.task_id for e in queue.pending()])
        with self.assertRaises(QueueFull):
            queue.put(envelope("c"))
        self.assertTrue(queue.full)

    def test_duplicate_key_rejected(self):
        queue = BoundedTaskQueue()
        queue.put(envelope("a", key="k"))
        with self.assertRaises(DuplicateTask):
            queue.put(envelope("b", key="k"))

    def test_key_not_replayable_after_pop(self):
        queue = BoundedTaskQueue()
        queue.put(envelope("a"))
        queue.pop()
        with self.assertRaises(DuplicateTask):
            queue.put(envelope("a"))

    def test_key_not_replayable_after_remove(self):
        queue = BoundedTaskQueue()
        queue.put(envelope("a"))
        self.assertTrue(queue.remove("a"))
        with self.assertRaises(DuplicateTask):
            queue.put(envelope("a"))

    def test_remove_unknown_is_false(self):
        self.assertFalse(BoundedTaskQueue().remove("nope"))

    def test_the_bounded_window_keeps_dispatch_working(self):
        queue = BoundedTaskQueue(maxsize=8)
        queue._history_limit = 3
        for index in range(3):
            queue.put(envelope("k{}".format(index)))
            queue.pop()
        # the window holds the newest three consumed keys
        self.assertEqual(["k0", "k1", "k2"], list(queue._history))
        # a pop never fails for the bookkeeping limit, and never loses an item
        queue.put(envelope("k9"))
        popped = queue.pop()
        self.assertEqual("k9", popped.task_id)
        self.assertEqual([], [e.task_id for e in queue.pending()])
        self.assertEqual(["k1", "k2", "k9"], list(queue._history))
        # the oldest key left the window; the durable store remains the
        # authoritative replay guard
        queue.put(envelope("k0"))
        self.assertEqual("k0", queue.pop().task_id)

    def test_history_cap_rejects_safely(self):
        queue = BoundedTaskQueue(maxsize=2)
        queue._history_limit = 3  # bounded replay history
        for i in range(3):
            queue.put(envelope("k{}".format(i)))
            queue.pop()
        with self.assertRaises(DuplicateTask):
            queue.put(envelope("k0"))

    def test_peek_and_empty(self):
        queue = BoundedTaskQueue()
        self.assertIsNone(queue.peek())
        self.assertIsNone(queue.pop())
        queue.put(envelope("a"))
        self.assertEqual("a", queue.peek().task_id)

    def test_bad_maxsize_rejected(self):
        from boru.errors import ContractError

        for bad in (0, True, "5", -1):
            with self.assertRaises(ContractError):
                BoundedTaskQueue(maxsize=bad)


if __name__ == "__main__":
    unittest.main()
