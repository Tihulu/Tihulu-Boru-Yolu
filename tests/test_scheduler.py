"""Agent scheduler tests: logical limits, DAG order and Boru-owned leases."""
import unittest

from boru.errors import PolicyViolation
from boru.config import CoreConfig, ProviderConfig
from boru.core import BoruCore
from boru.policy import Policy
from boru.scheduler import AgentScheduler, AgentSpec, build_envelopes
from boru.state import TaskState

def states(tasks, state=TaskState.QUEUED):
    return {task: state for task in tasks}


class SchedulerTests(unittest.TestCase):
    def build(self, specs, policy=None, **kwargs):
        scheduler = AgentScheduler(policy or Policy(), **kwargs)
        scheduler.add_many(specs)
        return scheduler

    def test_dag_order_respects_dependencies(self):
        scheduler = self.build([
            AgentSpec("plan", "p1"),
            AgentSpec("plan", "p2"),
            AgentSpec("plan", "p3", depends_on=("p1", "p2")),
        ])
        current = states(scheduler.tasks())
        self.assertEqual(["p1", "p2"], scheduler.ready(current))
        self.assertEqual(["p3"], scheduler.blocked(current))
        current["p1"] = TaskState.DONE
        self.assertEqual(["p2"], scheduler.ready(current))
        current["p2"] = TaskState.DONE
        self.assertEqual(["p3"], scheduler.ready(current))
        current["p3"] = TaskState.DONE
        self.assertEqual([], scheduler.ready(current))
        self.assertEqual([], scheduler.blocked(current))

    def test_six_logical_agent_ceiling(self):
        scheduler = AgentScheduler(Policy(max_agents=6))
        for index in range(6):
            scheduler.add(AgentSpec("a{}".format(index), "t{}".format(index)))
        for task_id in scheduler.tasks():
            spec = scheduler.spec(task_id)
            scheduler.acquire(spec)
        self.assertEqual(6, scheduler.leases.agents_active)
        extra = AgentSpec("extra", "t6")
        with self.assertRaises(PolicyViolation):
            scheduler.acquire(extra)
        for task_id in list(scheduler.tasks()):
            scheduler.release(task_id)
        self.assertEqual(0, scheduler.leases.agents_active)

    def test_more_than_six_agents_rejected(self):
        for bad in (0, 7, True, "6"):
            with self.assertRaises(PolicyViolation):
                AgentScheduler(Policy(), max_agents=bad)

    def test_large_local_model_lease_is_one_by_default(self):
        scheduler = self.build([
            AgentSpec("build", "b1", large_local_model=True),
            AgentSpec("build", "b2", large_local_model=True),
        ], max_large_local_models=1)
        scheduler.acquire(scheduler.spec("b1"))
        allowed, reason = scheduler.can_lease(scheduler.spec("b2"))
        self.assertFalse(allowed)
        self.assertEqual("large_local_model_limit", reason)
        scheduler.release("b1")
        allowed, reason = scheduler.can_lease(scheduler.spec("b2"))
        self.assertTrue(allowed)
        scheduler.acquire(scheduler.spec("b2"))
        self.assertEqual(1, scheduler.leases.large_local_models)
        scheduler.release("b2")
        self.assertEqual(0, scheduler.leases.large_local_models)

    def test_bad_large_model_limit_rejected(self):
        for bad in (3, True, -1):
            with self.assertRaises(PolicyViolation):
                AgentScheduler(Policy(), max_large_local_models=bad)

    def test_unknown_dependency_rejected(self):
        with self.assertRaises(PolicyViolation):
            self.build([AgentSpec("a", "a", depends_on=("missing",))])

    def test_self_dependency_rejected(self):
        with self.assertRaises(PolicyViolation):
            self.build([AgentSpec("a", "a", depends_on=("a",))])

    def test_duplicate_task_rejected(self):
        with self.assertRaises(PolicyViolation):
            self.build([AgentSpec("a", "a"), AgentSpec("a", "a")])

    def test_plan_is_bounded(self):
        specs = [AgentSpec("a", "t{}".format(i)) for i in range(65)]
        with self.assertRaises(PolicyViolation):
            self.build(specs)

    def test_bad_spec_rejected(self):
        for bad in (dict(agent_id="", task_id="t"), dict(task_id=""),
                    dict(capability_tags=("ok", "")), dict(depends_on="a"), dict(large_local_model=1)):
            kwargs = {"agent_id": "a", "task_id": "t"}
            kwargs.update(bad)
            with self.assertRaises(PolicyViolation):
                self.build([AgentSpec(**kwargs)])

    def test_release_is_idempotent_and_only_touches_owned_leases(self):
        scheduler = self.build([AgentSpec("a", "a", large_local_model=True)])
        scheduler.acquire(scheduler.spec("a"))
        scheduler.release("a")
        scheduler.release("a")
        self.assertEqual(0, scheduler.leases.agents_active)
        self.assertEqual(0, scheduler.leases.large_local_models)

    def test_build_envelopes_inherit_safety_defaults(self):
        envelopes = build_envelopes([AgentSpec("a", "a", capability_tags=("text",))], "goal")
        envelope = envelopes[0]
        self.assertEqual("LOCAL_ONLY", envelope.inference_scope)
        self.assertEqual("LOCAL_ISOLATED", envelope.execution_profile)
        self.assertEqual(("text",), envelope.capability_tags)
        self.assertEqual("a", envelope.task_id)


if __name__ == "__main__":
    unittest.main()


class CorePlanTests(unittest.TestCase):
    """Plan submission and DAG-aware dispatch through BoruCore."""

    def setUp(self):
        self.engine = BoruCore(CoreConfig(providers=(ProviderConfig(kind="mock"),)))

    def tearDown(self):
        self.engine.close()

    def test_plan_runs_in_dependency_order(self):
        specs = [AgentSpec("w", "gather", capability_tags=("text",)),
                 AgentSpec("w", "plan", depends_on=("gather",), capability_tags=("text",)),
                 AgentSpec("w", "report", depends_on=("plan",), capability_tags=("text",))]
        self.engine.submit_plan(specs, "synthetic plan")
        states = self.engine.plan_states()
        self.assertEqual("QUEUED", states["gather"].value)
        summary = self.engine.dispatch_ready()
        self.assertEqual("gather", summary["task_id"])
        self.assertEqual("REVIEW", summary["state"])
        self.engine.review("gather", accept=True)
        summary = self.engine.dispatch_ready()
        self.assertEqual("plan", summary["task_id"])
        self.engine.review("plan", accept=True)
        summary = self.engine.dispatch_ready()
        self.assertEqual("report", summary["task_id"])
        self.engine.review("report", accept=True)
        self.assertIsNone(self.engine.dispatch_ready())

    def test_plan_blocked_until_dependency_done(self):
        specs = [AgentSpec("w", "gather"), AgentSpec("w", "next", depends_on=("gather",))]
        self.engine.submit_plan(specs, "synthetic")
        summary = self.engine.dispatch_ready()
        self.assertEqual("gather", summary["task_id"])
        self.assertEqual("REVIEW", summary["state"])
        # not accepted yet: the dependent task must not run
        self.assertEqual("QUEUED", self.engine.plan_states()["next"].value)
        blocked = self.engine.scheduler.blocked(self.engine.plan_states())
        self.assertIn("next", blocked)

    def test_lease_limit_holds_extra_large_model_task(self):
        specs = [AgentSpec("w", "heavy-a", large_local_model=True),
                 AgentSpec("w", "heavy-b", large_local_model=True)]
        self.engine.submit_plan(specs, "synthetic")
        self.engine.scheduler.max_large_local_models = 1
        summary = self.engine.dispatch_ready()
        self.assertEqual("heavy-a", summary["task_id"])
        self.engine.review("heavy-a", accept=True)
        state = self.engine.plan_states()["heavy-b"]
        self.assertEqual("QUEUED", state.value)

    def test_plan_is_bounded(self):
        specs = [AgentSpec("w", "t{}".format(index)) for index in range(65)]
        with self.assertRaises(PolicyViolation):
            self.engine.submit_plan(specs, "synthetic")

    def test_concurrent_agents_stay_within_six(self):
        specs = [AgentSpec("w", "t{}".format(index)) for index in range(6)]
        self.engine.submit_plan(specs, "synthetic")
        self.assertEqual(6, self.engine.scheduler.max_agents)
