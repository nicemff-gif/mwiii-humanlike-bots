import unittest

from tools.check_repository import path_problem


class PublicationBoundaryTests(unittest.TestCase):
    def test_rejects_payloads_and_private_state(self):
        for path in [
            "game/XInput9_1_0.dll", "src/bots.gscc", "zone/map.ff",
            "profiles/settings.json", ".env", ".env.production", "config.local.json",
            "dist/manifest.json", "references/private/notes.md",
            "research/bots.decompiled.gsc.txt", "../outside.txt", "C:/game/file.txt",
        ]:
            with self.subTest(path=path):
                self.assertIsNotNone(path_problem(path))

    def test_accepts_original_source_and_documentation(self):
        for path in ["src/hbot/probe.gsc", "docs/testing.md", ".env.example", "tests/test_build.py"]:
            with self.subTest(path=path):
                self.assertIsNone(path_problem(path))


if __name__ == "__main__":
    unittest.main()
