import struct
import unittest

from tools.build import MAGIC, OPT_IN_FLAGS, profile_source, validate_gsc, validate_inspection, validate_memory_source, validate_diagnostics_source, validate_decision_source


class GscArtifactBoundaryTests(unittest.TestCase):
    def object(self):
        payload = bytearray(0x68)
        payload[:8] = MAGIC
        struct.pack_into("<II", payload, 0x34, 0x60, 8)
        struct.pack_into("<I", payload, 0x48, len(payload))
        return payload

    def test_rejects_wrong_vm_and_truncated_input(self):
        for payload in [b"", b"MZ" + bytes(120), MAGIC + bytes(10)]:
            with self.subTest(size=len(payload)), self.assertRaises(ValueError):
                validate_gsc(payload)

    def test_rejects_code_outside_object_and_trailing_data(self):
        payload = self.object()
        struct.pack_into("<I", payload, 0x38, 0x100)
        with self.assertRaises(ValueError):
            validate_gsc(payload)
        with self.assertRaises(ValueError):
            validate_gsc(self.object() + b"extra")

    def test_accepts_bounded_object(self):
        validate_gsc(self.object())


class ProbeInspectionTests(unittest.TestCase):
    def baseline(self):
        return (
            "#namespace hbot_probe;\n// Namespace hbot_probe / hbot_probe\nfunction autoexec __init__system__()\n"
            "function observe_match()\ngetdvarint( @\"hbot_probe_enabled\", 0 )\n"
            "#namespace hbot_memory;\n#namespace hbot_mode;\n#namespace hbot_perception;\n#namespace hbot_contracts;\n"
            "#namespace hbot_diagnostics;\ngetdvarint( @\"hbot_debug_enabled\", 0 )\n"
            "#namespace hbot_decision;\nfunction run_decision_contracts()\nhbot_decision::update(\n"
            "hbot_mode::supports_tdm(\nhbot_memory::record_visible(\n"
            "getdvarint( @\"hbot_memory_enabled\", 0 )\ngetdvarint( @\"hbot_memory_selftest\", 0 )\n"
            "level endon( \"game_ended\" );\n// dev strs .. 0   (offset: 0x100)\n"
        )

    def test_default_enabled_probe_fails_gate(self):
        changed = self.baseline().replace('"hbot_probe_enabled", 0', '"hbot_probe_enabled", 1')
        with self.assertRaises(ValueError):
            validate_inspection(changed)

    def test_mutating_and_unresolved_calls_fail_gate(self):
        for call in ["botpressbutton(", "setorigin(", "setplayerangles(", "function_deadbeef1234()", "<dev string>"]:
            with self.subTest(call=call), self.assertRaises(ValueError):
                validate_inspection(self.baseline() + call)

    def test_observer_contract_passes(self):
        validate_inspection(self.baseline())

    def test_memory_domain_cannot_read_engine_state(self):
        for read in ["level.players", "self.origin", "gettime()", "sighttracepassed(a,b,0,c)"]:
            with self.subTest(read=read), self.assertRaises(ValueError):
                validate_memory_source(read)
        validate_memory_source("// level state is intentionally absent\n contact = spawnstruct();")

    def test_diagnostics_cannot_export_hidden_positions_or_resample(self):
        for read in ["target.origin", "target geteye()", "sample_visible(a,b)", "record_visible(a,b,c,d)", "sighttracepassed(a,b,0,c)"]:
            with self.subTest(read=read), self.assertRaises(ValueError):
                validate_diagnostics_source(read)
        validate_diagnostics_source("// origin is deliberately absent\ncontact = hbot_memory::recall(memory, id, now);")

    def test_default_enabled_diagnostics_fails_gate(self):
        changed = self.baseline().replace('"hbot_debug_enabled", 0', '"hbot_debug_enabled", 1')
        with self.assertRaises(ValueError):
            validate_inspection(changed)

    def test_manual_test_fallbacks_require_explicit_matching_profile(self):
        original = self.baseline()
        prepared = profile_source(original, "manual-test")
        expected = original
        for flag in OPT_IN_FLAGS:
            expected = expected.replace(f'getdvarint( @"{flag}", 0 )', f'getdvarint( @"{flag}", 1 )')
        self.assertEqual(prepared, expected)
        self.assertEqual(profile_source(original, "observer"), original)
        validate_inspection(prepared, "manual-test")
        with self.assertRaises(ValueError):
            validate_inspection(prepared)
        with self.assertRaises(ValueError):
            validate_inspection(original, "manual-test")

    def test_profile_transform_rejects_drift_duplicates_and_unknown_profile(self):
        original = self.baseline()
        for source, profile in [(original, "unknown"), (original + original, "manual-test"), (original.replace('"hbot_probe_enabled", 0', '"hbot_probe_enabled", 1'), "manual-test")]:
            with self.subTest(profile=profile), self.assertRaises(ValueError):
                profile_source(source, profile)

    def test_decisions_cannot_access_world_geometry_entities_or_controls(self):
        for read in ["level.players", "self.origin", "gettime()", "hbot_perception::sample_visible(a,b)", "hbot_memory::record_visible(m,i,p,t)", "botpressbutton(a)", "iprintln(x)"]:
            with self.subTest(read=read), self.assertRaises(ValueError):
                validate_decision_source(read)
        validate_decision_source("contact = hbot_memory::recall(memory, id, now);")


if __name__ == "__main__":
    unittest.main()
