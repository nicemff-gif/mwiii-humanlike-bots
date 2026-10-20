import hashlib
import json
import os
from pathlib import Path
import stat
import struct
import subprocess
import tempfile
import unittest
from unittest import mock

from tools.build import MAGIC
from tools import deploy


class DeploymentTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="hbot-deploy-test-")
        self.addCleanup(self.temporary.cleanup)
        # GitHub Windows runners may expose TEMP through an 8.3 path alias.
        self.root = Path(self.temporary.name).resolve()
        self.game = self.root / "game"
        self.target = self.game / deploy.INSTALL_PATH
        self.target.parent.mkdir(parents=True)
        (self.game / "cod23-cod.exe").write_bytes(b"test marker; not executable")
        self.settings = self.game / "jupiter" / "settings.json"
        self.settings.write_bytes(b'{"preserve":"player settings"}')
        self.unrelated = self.target.parent / "third_party.gscc"
        self.unrelated.write_bytes(b"preserve third-party script")
        self.package = self.root / "package"
        self.package.mkdir()
        self.artifact = self.package / deploy.ARTIFACT_NAME
        payload = bytearray(0x68)
        payload[:8] = MAGIC
        struct.pack_into("<II", payload, 0x34, 0x60, 8)
        struct.pack_into("<I", payload, 0x48, len(payload))
        payload[0x60:] = b"fixture1"
        self.payload = bytes(payload)
        self.artifact.write_bytes(self.payload)
        self.manifest = self.package / "manifest.json"
        self.metadata = {
            "schema_version": 1,
            "source_commit": "a" * 40,
            "working_tree_dirty": False,
            "repeated_build_identical": True,
            "validation": {"compile": "pass", "inspection": "pass"},
            "artifacts": [{
                "path": deploy.ARTIFACT_NAME,
                "install_path": deploy.INSTALL_PATH,
                "bytes": len(self.payload),
                "sha256": hashlib.sha256(self.payload).hexdigest(),
            }],
        }
        self.write_manifest()
        self.state = self.root / "state"

    def write_manifest(self):
        self.manifest.write_text(json.dumps(self.metadata), encoding="utf-8")

    def apply(self, guard=lambda: None):
        return deploy.apply(self.manifest, self.game, self.state, guard=guard)

    def rollback(self, result, guard=lambda: None):
        return deploy.rollback(Path(result["receipt"]), self.game, guard=guard)

    def assert_unrelated_preserved(self):
        self.assertEqual(self.settings.read_bytes(), b'{"preserve":"player settings"}')
        self.assertEqual(self.unrelated.read_bytes(), b"preserve third-party script")
        self.assertFalse((self.game / ".hbot-deploy.lock").exists())

    def test_preview_has_no_filesystem_mutations(self):
        before = {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        result = deploy.plan(self.manifest, self.game)
        after = {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        self.assertEqual(result["action"], "install")
        self.assertEqual(result["runtime_validation"], "not_run")
        self.assertEqual(before, after)
        self.assertFalse(self.state.exists())

    def test_first_install_and_rollback_preserve_other_files(self):
        guard = mock.Mock()
        result = self.apply(guard)
        self.assertEqual(self.target.read_bytes(), self.payload)
        self.assertEqual(guard.call_count, 2)
        receipt = json.loads(Path(result["receipt"]).read_text())
        self.assertEqual(receipt["state"], "installed")
        self.assertFalse(receipt["original_existed"])
        self.assertEqual(self.rollback(result)["status"], "rolled_back")
        self.assertFalse(self.target.exists())
        self.assert_unrelated_preserved()

    def test_replacement_backs_up_and_restores_original_bytes(self):
        self.target.write_bytes(b"original probe")
        self.assertEqual(deploy.plan(self.manifest, self.game)["action"], "replace")
        result = self.apply()
        backup = Path(result["receipt"]).parent / "original.gscc"
        self.assertEqual(backup.read_bytes(), b"original probe")
        self.rollback(result)
        self.assertEqual(self.target.read_bytes(), b"original probe")
        self.assert_unrelated_preserved()

    def test_identical_deployment_is_idempotent(self):
        self.apply()
        self.assertEqual(self.apply(), {"status": "already_present", "receipt": None})
        self.assertEqual(len(list(self.state.glob("*/receipt.json"))), 1)
        self.assertEqual(deploy.plan(self.manifest, self.game)["action"], "already_present")

    def test_repeated_rollback_does_not_remove_later_external_files(self):
        result = self.apply()
        self.rollback(result)
        self.target.write_bytes(b"later independent installation")
        self.assertEqual(self.rollback(result)["status"], "already_rolled_back")
        self.assertEqual(self.target.read_bytes(), b"later independent installation")

    def test_tampered_artifact_is_rejected_before_game_mutation(self):
        self.artifact.write_bytes(self.payload + b"tamper")
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            self.apply()
        self.assertFalse(self.target.exists())
        self.assertFalse(self.state.exists())
        self.assert_unrelated_preserved()

    def test_manifest_cannot_write_other_scripts_or_player_settings(self):
        for path in ["../outside.gscc", "jupiter/settings.json", "jupiter/Assets/Scripts/mp/matchstats.gscc"]:
            with self.subTest(path=path):
                self.metadata["artifacts"][0]["install_path"] = path
                self.write_manifest()
                with self.assertRaisesRegex(ValueError, "allowlist"):
                    self.apply()
        self.assert_unrelated_preserved()

    def test_dirty_or_unverified_build_cannot_be_installed(self):
        for key, value in [("working_tree_dirty", True), ("repeated_build_identical", False)]:
            with self.subTest(key=key):
                previous = self.metadata[key]
                self.metadata[key] = value
                self.write_manifest()
                with self.assertRaises(ValueError):
                    self.apply()
                self.metadata[key] = previous
        self.metadata["validation"]["inspection"] = "not_run"
        self.write_manifest()
        with self.assertRaises(ValueError):
            self.apply()
        self.assertFalse(self.state.exists())

    def test_external_edit_blocks_rollback_without_overwriting_edit(self):
        self.target.write_bytes(b"original")
        result = self.apply()
        self.target.write_bytes(b"edited by another tool")
        with self.assertRaisesRegex(RuntimeError, "changed outside"):
            self.rollback(result)
        self.assertEqual(self.target.read_bytes(), b"edited by another tool")
        self.assertEqual(json.loads(Path(result["receipt"]).read_text())["state"], "installed")
        self.assert_unrelated_preserved()

    def test_corrupted_backup_blocks_rollback_without_overwriting_target(self):
        self.target.write_bytes(b"original")
        result = self.apply()
        (Path(result["receipt"]).parent / "original.gscc").write_bytes(b"tampered backup")
        with self.assertRaisesRegex(ValueError, "backup"):
            self.rollback(result)
        self.assertEqual(self.target.read_bytes(), self.payload)

    def test_running_game_guard_prevents_apply_and_rollback(self):
        blocked = mock.Mock(side_effect=RuntimeError("game running"))
        with self.assertRaisesRegex(RuntimeError, "game running"):
            self.apply(blocked)
        self.assertFalse(self.state.exists())
        result = self.apply()
        with self.assertRaisesRegex(RuntimeError, "game running"):
            self.rollback(result, blocked)
        self.assertEqual(self.target.read_bytes(), self.payload)
        self.assert_unrelated_preserved()

    def test_late_game_start_leaves_recoverable_prepared_receipt(self):
        blocked = mock.Mock(side_effect=[None, RuntimeError("game started")])
        with self.assertRaisesRegex(RuntimeError, "game started"):
            self.apply(blocked)
        receipt = next(self.state.glob("*/receipt.json"))
        self.assertFalse(self.target.exists())
        self.assertEqual(json.loads(receipt.read_text())["state"], "prepared")
        self.assertEqual(self.rollback({"receipt": str(receipt)})["status"], "already_restored")

    def test_atomic_replace_failure_keeps_original_and_recovery_record(self):
        self.target.write_bytes(b"original")
        real_replace = os.replace

        def fail_target(source, destination):
            if Path(destination).resolve() == self.target.resolve():
                raise OSError("simulated disk failure")
            return real_replace(source, destination)

        with mock.patch("tools.deploy.os.replace", side_effect=fail_target):
            with self.assertRaisesRegex(OSError, "disk failure"):
                self.apply()
        self.assertEqual(self.target.read_bytes(), b"original")
        receipt = next(self.state.glob("*/receipt.json"))
        self.assertEqual(self.rollback({"receipt": str(receipt)})["status"], "already_restored")
        self.assertEqual(list(self.target.parent.glob(".hbot-*")), [])
        self.assert_unrelated_preserved()

    def test_interrupted_receipt_update_can_roll_back_installed_payload(self):
        original_write = deploy.write_receipt
        calls = 0

        def interrupted(path, receipt):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("interrupted after replacement")
            return original_write(path, receipt)

        with mock.patch("tools.deploy.write_receipt", side_effect=interrupted):
            with self.assertRaises(OSError):
                self.apply()
        receipt = next(self.state.glob("*/receipt.json"))
        self.assertEqual(json.loads(receipt.read_text())["state"], "prepared")
        self.assertEqual(self.target.read_bytes(), self.payload)
        self.assertEqual(self.rollback({"receipt": str(receipt)})["status"], "rolled_back")
        self.assertFalse(self.target.exists())

    def test_existing_lock_is_preserved(self):
        lock = self.game / ".hbot-deploy.lock"
        lock.write_text("another transaction", encoding="ascii")
        with self.assertRaisesRegex(RuntimeError, "lock"):
            self.apply()
        self.assertEqual(lock.read_text(), "another transaction")
        self.assertFalse(self.state.exists())

    def test_target_edit_during_apply_is_preserved(self):
        self.target.write_bytes(b"original")
        calls = 0

        def external_edit():
            nonlocal calls
            calls += 1
            if calls == 2:
                self.target.write_bytes(b"concurrent edit")

        with self.assertRaisesRegex(RuntimeError, "changed during deployment"):
            self.apply(external_edit)
        self.assertEqual(self.target.read_bytes(), b"concurrent edit")
        self.assertEqual(next(self.state.glob("*/original.gscc")).read_bytes(), b"original")

    def test_target_edit_during_rollback_is_preserved(self):
        result = self.apply()
        calls = 0

        def external_edit():
            nonlocal calls
            calls += 1
            if calls == 2:
                self.target.write_bytes(b"concurrent edit")

        with self.assertRaisesRegex(RuntimeError, "changed during rollback"):
            self.rollback(result, external_edit)
        self.assertEqual(self.target.read_bytes(), b"concurrent edit")

    def test_wrong_root_and_in_game_receipts_are_rejected(self):
        result = self.apply()
        other = self.root / "other-game"
        (other / "jupiter/Assets/Scripts").mkdir(parents=True)
        (other / "cod23-cod.exe").write_bytes(b"marker")
        with self.assertRaisesRegex(ValueError, "does not belong"):
            deploy.rollback(Path(result["receipt"]), other, guard=lambda: None)
        with self.assertRaisesRegex(ValueError, "outside"):
            deploy.apply(self.manifest, self.game, self.game / "receipts", guard=lambda: None)

    def test_symlink_parent_is_rejected_and_external_files_preserved(self):
        outside = self.root / "outside"
        outside.mkdir()
        sentinel = outside / "preserve.txt"
        sentinel.write_bytes(b"outside content")
        # The existing MP directory has a fixture; move it within this temporary tree.
        real_mp = self.game / "real-mp"
        self.target.parent.rename(real_mp)
        try:
            self.target.parent.symlink_to(outside, target_is_directory=True)
        except OSError:
            real_mp.rename(self.target.parent)
            self.skipTest("This Windows account cannot create symbolic links")
        with self.assertRaisesRegex(ValueError, "reparse|links"):
            self.apply()
        self.assertEqual(sentinel.read_bytes(), b"outside content")
        self.assertFalse((outside / deploy.ARTIFACT_NAME).exists())

    @unittest.skipUnless(os.name == "nt", "Windows junction integration test")
    def test_windows_junction_cannot_redirect_deployment(self):
        outside = self.root / "junction-outside"
        outside.mkdir()
        sentinel = outside / "preserve.txt"
        sentinel.write_bytes(b"outside content")
        original_mp = self.game / "original-mp"
        self.target.parent.rename(original_mp)
        env = os.environ.copy()
        env.update(HBOT_TEST_LINK=str(self.target.parent), HBOT_TEST_OUTSIDE=str(outside))
        try:
            subprocess.run(
                ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
                 "New-Item -ItemType Junction -Path $env:HBOT_TEST_LINK -Target $env:HBOT_TEST_OUTSIDE -ErrorAction Stop | Out-Null"],
                env=env, capture_output=True, check=True, timeout=15,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            with self.assertRaisesRegex(ValueError, "reparse"):
                self.apply()
            self.assertEqual(sentinel.read_bytes(), b"outside content")
            self.assertFalse((outside / deploy.ARTIFACT_NAME).exists())
        finally:
            # Both paths were created inside this test's verified temporary root.
            self.assertTrue(self.target.parent.absolute().is_relative_to(self.root.absolute()))
            if self.target.parent.exists():
                self.target.parent.rmdir()
            original_mp.rename(self.target.parent)


class ProcessAndPathTests(unittest.TestCase):
    def test_relative_path_tricks_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            for name in [".", "../outside", "/outside", "C:/outside", "a\\b", "a/../b", "a//b"]:
                with self.subTest(name=name), self.assertRaises(ValueError):
                    deploy.safe_child(Path(directory), name)

    @mock.patch("tools.deploy.sys.platform", "win32")
    def test_process_names_are_checked_case_insensitively(self):
        result = subprocess.CompletedProcess([], 0, '"CoD23-CoD.exe","123","Console","1","10 K"\n', "")
        with mock.patch("tools.deploy.subprocess.run", return_value=result):
            with self.assertRaisesRegex(RuntimeError, "Close the game"):
                deploy.ensure_game_stopped()

    @mock.patch("tools.deploy.sys.platform", "win32")
    def test_empty_or_unreadable_inventory_fails_closed(self):
        for output in ["", "process query unavailable"]:
            with self.subTest(output=output):
                result = subprocess.CompletedProcess([], 0, output, "")
                with mock.patch("tools.deploy.subprocess.run", return_value=result):
                    with self.assertRaisesRegex(RuntimeError, "inventory"):
                        deploy.ensure_game_stopped()

    @mock.patch("tools.deploy.sys.platform", "win32")
    def test_non_game_processes_allow_operation(self):
        result = subprocess.CompletedProcess([], 0, '"System","4","Services","0","10 K"\n', "")
        with mock.patch("tools.deploy.subprocess.run", return_value=result):
            deploy.ensure_game_stopped()

    def test_windows_reparse_attributes_are_rejected(self):
        point = type("Info", (), {"st_mode": stat.S_IFDIR, "st_file_attributes": 1024})()
        with mock.patch.object(Path, "lstat", return_value=point):
            with mock.patch.object(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 1024, create=True):
                with self.assertRaisesRegex(ValueError, "reparse"):
                    deploy.reject_links(Path("junction"))


if __name__ == "__main__":
    unittest.main()
