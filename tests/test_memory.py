from dataclasses import FrozenInstanceError
import json
from pathlib import Path
import unittest

from model.memory import TargetMemory, supports_tdm
from tools.generate_contracts import generate


SCENARIOS = json.loads((Path(__file__).parent / "fixtures/memory_scenarios.json").read_text(encoding="utf-8"))


class SharedMemoryContractTests(unittest.TestCase):
    def test_reference_model_satisfies_all_shared_scenarios(self):
        for case in SCENARIOS["cases"]:
            with self.subTest(case=case["name"]):
                memory = TargetMemory(case["ttl_ms"], case["capacity"])
                for index, step in enumerate(case["steps"]):
                    with self.subTest(step=index):
                        if step["op"] == "see":
                            accepted = memory.record_visible(step["id"], step["position"], step["now_ms"])
                            self.assertEqual(accepted, step.get("accepted", True))
                        elif step["op"] == "hidden":
                            # The new world position is intentionally never supplied.
                            memory.advance(step["now_ms"])
                        elif step["op"] == "reset":
                            memory.clear()
                        elif step["op"] == "expect":
                            contact = memory.recall(step["id"], step["now_ms"])
                            expected = step["contact"]
                            if expected is None:
                                self.assertIsNone(contact)
                            else:
                                self.assertIsNotNone(contact)
                                self.assertEqual(contact.position, tuple(expected["position"]))
                                self.assertEqual(contact.seen_at, expected["seen_at"])
                                self.assertAlmostEqual(contact.confidence, expected["confidence"])
                        else:
                            self.fail("Unknown scenario operation")

    def test_hidden_world_changes_do_not_change_contact(self):
        memories = [TargetMemory(), TargetMemory()]
        for memory in memories:
            memory.record_visible(1, [10, 20, 30], 0)
        hidden_worlds = [[900, 0, 0], [-900, 800, 0]]
        for world_position, memory in zip(hidden_worlds, memories):
            self.assertNotEqual(world_position, [10, 20, 30])
            memory.advance(500)
        self.assertEqual(memories[0].recall(1, 1000), memories[1].recall(1, 1000))

    def test_input_and_returned_contact_cannot_mutate_stored_position(self):
        memory = TargetMemory()
        position = [10, 20, 30]
        memory.record_visible(1, position, 0)
        position[0] = 999
        contact = memory.recall(1, 0)
        self.assertEqual(contact.position, (10, 20, 30))
        with self.assertRaises(FrozenInstanceError):
            contact.position = (999, 0, 0)

    def test_observers_have_independent_memory(self):
        first, second = TargetMemory(), TargetMemory()
        first.record_visible(1, [1, 0, 0], 0)
        self.assertIsNone(second.recall(1, 0))

    def test_invalid_dimensions_use_bounded_defaults(self):
        memory = TargetMemory(ttl_ms=-1, capacity=100000)
        self.assertEqual((memory.ttl_ms, memory.capacity), (4000, 16))

    def test_nonfinite_or_malformed_positions_are_rejected(self):
        for position in [[float("nan"), 0, 0], [float("inf"), 0, 0], [1, 2], ["x", 0, 0]]:
            with self.subTest(position=position):
                memory = TargetMemory()
                self.assertFalse(memory.record_visible(1, position, 0))
                self.assertIsNone(memory.recall(1, 0))


class ModeBoundaryTests(unittest.TestCase):
    def test_only_initial_small_tdm_is_allowed(self):
        for case in SCENARIOS["mode_cases"]:
            with self.subTest(case=case):
                self.assertEqual(supports_tdm(case["mode"], case["teambased"], case["count"]), case["allowed"])


class NativeContractGenerationTests(unittest.TestCase):
    def test_every_reference_expectation_is_emitted_to_native_selftest(self):
        generated = generate(SCENARIOS)
        assertions = len(SCENARIOS["mode_cases"]) + sum(step["op"] in {"see", "expect"} for case in SCENARIOS["cases"] for step in case["steps"])
        self.assertEqual(generated.count("    check( report,"), assertions)
        self.assertNotIn("999, 999", generated)
        self.assertIn("run_memory_contracts", generated)

    def test_contract_generator_rejects_code_injection_and_invalid_values(self):
        for mutate in [
            lambda data: data["cases"][0].update(name="injected\ncode"),
            lambda data: data["cases"][0]["steps"].append({"op": "execute", "now_ms": 0}),
            lambda data: data["cases"][1]["steps"][0].update(position=[1, 2]),
            lambda data: data["cases"][0].update(ttl_ms=float("inf")),
        ]:
            data = json.loads(json.dumps(SCENARIOS))
            mutate(data)
            with self.assertRaises(ValueError):
                generate(data)


if __name__ == "__main__":
    unittest.main()
