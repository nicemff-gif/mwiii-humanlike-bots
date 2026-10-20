from dataclasses import FrozenInstanceError, asdict
import json
from pathlib import Path
import random
import unittest

from model.decision import Sample, ShadowDecision
from model.memory import TargetMemory
from tools.generate_decision_contracts import generate

SCENARIOS = json.loads((Path(__file__).parent / "fixtures/decision_scenarios.json").read_text(encoding="utf-8"))


def run_step(control, memory, step):
    if step["op"] == "reset":
        memory.clear()
        control.reset()
        return None
    now = step["now_ms"]
    if step["op"] == "seed":
        memory.record_visible(step["id"], step["position"], now)
        return None
    samples = []
    for event in step.get("samples", []):
        if event["visible"] and event.get("record", True):
            memory.record_visible(event["id"], event["position"], now)
        samples.append(Sample(event["id"], event["visible"], event.get("at_ms", now)))
    return control.update(memory, samples, now)


class DecisionContractTests(unittest.TestCase):
    def test_all_shared_scenarios_and_intent_invariants(self):
        for case in SCENARIOS["cases"]:
            control = ShadowDecision(*(case.get(key, default) for key, default in [("reaction_ms", 250), ("search_ms", 3000), ("stale_ms", 2000)]))
            memory = TargetMemory(case.get("ttl_ms", 4000), case.get("capacity", 16))
            for index, step in enumerate(case["steps"]):
                with self.subTest(case=case["name"], step=index):
                    intent = run_step(control, memory, step)
                    if intent is None:
                        continue
                    actual = asdict(intent)
                    actual["id"] = actual.pop("target_id")
                    for key, value in step["expect"].items():
                        self.assertEqual(actual[key], tuple(value) if key == "position" and value is not None else value)
                    if intent.position is not None:
                        self.assertIn(intent.state, ("tracking", "searching"))
                        self.assertEqual(intent.position, memory.recall(intent.target_id, step["now_ms"]).position)
                    if intent.state == "searching":
                        self.assertGreater(intent.search_remaining_ms, 0)
                        self.assertLessEqual(intent.search_remaining_ms, control.search_ms)
                    if intent.state == "idle":
                        self.assertIsNone(intent.target_id)
                        self.assertIsNone(intent.position)

    def test_hidden_world_changes_cannot_affect_intent(self):
        case = next(c for c in SCENARIOS["cases"] if c["name"] == "hidden-search-is-bounded")
        results = []
        for hidden in [(999, 888, 777), (-999, -888, -777)]:
            control, memory = ShadowDecision(), TargetMemory()
            outputs = []
            for step in case["steps"]:
                step = dict(step, world_position=hidden)
                outputs.append(run_step(control, memory, step))
            results.append(outputs)
        self.assertEqual(*results)

    def test_observers_and_returned_intents_are_independent(self):
        first, second = ShadowDecision(), ShadowDecision()
        memory, other_memory = TargetMemory(), TargetMemory()
        memory.record_visible(1, [1, 0, 0], 0)
        intent = first.update(memory, [Sample(1, True, 0)], 0)
        self.assertEqual(second.update(other_memory, [], 0).state, "idle")
        with self.assertRaises(FrozenInstanceError):
            intent.state = "tracking"

    def test_native_contract_covers_every_expected_field_without_hidden_coordinates(self):
        generated = generate(SCENARIOS)
        expected = sum(len(s.get("expect", {})) for c in SCENARIOS["cases"] for s in c["steps"])
        self.assertEqual(generated.count("    check( report,"), expected)
        self.assertNotIn("999, 888, 777", generated)
        self.assertNotIn("900, 900, 900", generated)

    def test_generator_rejects_injection_and_invalid_expectations(self):
        for mutate in [
            lambda d: d["cases"][0].update(name='bad";code'),
            lambda d: d["cases"][0]["steps"][0]["expect"].update(state='bad";code'),
            lambda d: d["cases"][0]["steps"][0]["expect"].update(hidden_position=[1, 2, 3]),
            lambda d: d["cases"][0].update(reaction_ms=float("inf")),
            lambda d: d["cases"][0]["steps"][1]["samples"][0].update(visible="yes"),
        ]:
            data = json.loads(json.dumps(SCENARIOS))
            mutate(data)
            with self.assertRaises(ValueError):
                generate(data)

    def test_replay_is_order_independent_and_never_bypasses_reaction(self):
        rng = random.Random(20261020)
        controls = [ShadowDecision(), ShadowDecision()]
        memories = [TargetMemory(), TargetMemory()]
        now = 0
        for _ in range(1000):
            now += rng.randrange(0, 151)
            events = [{"id": target, "visible": bool(rng.getrandbits(1)), "position": [rng.randrange(-50, 51), target, 0]} for target in rng.sample(range(1, 5), rng.randrange(3))]
            results = []
            for index, (control, memory) in enumerate(zip(controls, memories)):
                previous_state = control.state
                reaction_started = control.reaction_started_at
                ordered = events if index == 0 else list(reversed(events))
                step = {"op": "step", "now_ms": now, "samples": ordered}
                intent = run_step(control, memory, step)
                results.append(intent)
                if intent.state == "tracking" and previous_state != "tracking":
                    self.assertGreaterEqual(now - reaction_started, control.reaction_ms)
                    self.assertTrue(any(e["id"] == intent.target_id and e["visible"] for e in events))
                if intent.position is not None:
                    self.assertEqual(intent.position, memory.recall(intent.target_id, now).position)
                if intent.state in ("idle", "reacting"):
                    self.assertIsNone(intent.position)
                if intent.state == "searching":
                    self.assertGreater(intent.search_remaining_ms, 0)
                    self.assertLessEqual(intent.search_remaining_ms, control.search_ms)
            self.assertEqual(*results)


if __name__ == "__main__":
    unittest.main()
