import struct
import unittest

from tools.build import MAGIC, validate_gsc, validate_inspection


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
            "#namespace hbot_probe;\nfunction autoexec __init__system__()\n"
            "function observe_match()\ngetdvarint( @\"hbot_probe_enabled\", 0 )\n"
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


if __name__ == "__main__":
    unittest.main()
