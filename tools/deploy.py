"""Preview, deploy, and roll back the opt-in probe using a local receipt."""
import argparse
from contextlib import contextmanager
import csv
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import sys
import tempfile
from typing import Callable
import uuid

from tools.build import validate_gsc
from tools.toolchain import ROOT


INSTALL_PATH = "jupiter/Assets/Scripts/mp/hbot_probe.gscc"
ARTIFACT_NAME = "hbot_probe.gscc"
RECEIPT_KIND = "hbot-probe-deployment"
GAME_PROCESSES = {"cod23-cod.exe", "cod.exe", "bootstrapper.exe"}


def digest(data: bytes | None) -> str | None:
    return None if data is None else hashlib.sha256(data).hexdigest()


def reject_links(path: Path) -> None:
    absolute = path.absolute()
    for candidate in [*reversed(absolute.parents), absolute]:
        try:
            info = candidate.lstat()
        except FileNotFoundError:
            continue
        reparse = getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
        if stat.S_ISLNK(info.st_mode) or reparse:
            raise ValueError("Symbolic links and Windows reparse points are not valid deployment paths")


def safe_child(root: Path, name: str) -> Path:
    relative = PurePosixPath(name)
    if (
        not name or name == "." or "\\" in name or ":" in name or relative.is_absolute()
        or ".." in relative.parts or relative.as_posix() != name
    ):
        raise ValueError("Deployment paths must be canonical relative paths")
    child = root.joinpath(*relative.parts)
    reject_links(child)
    if not child.resolve().is_relative_to(root.resolve()):
        raise ValueError("Deployment path escapes its root")
    return child


def validate_game_root(path: Path) -> Path:
    reject_links(path)
    root = path.resolve(strict=True)
    marker = safe_child(root, "cod23-cod.exe")
    scripts = safe_child(root, "jupiter/Assets/Scripts")
    if not marker.is_file() or not scripts.is_dir():
        raise ValueError("Target must contain cod23-cod.exe and jupiter/Assets/Scripts")
    return root


def snapshot(path: Path) -> bytes | None:
    reject_links(path)
    if not path.exists():
        return None
    if not path.is_file():
        raise ValueError("Expected a regular file at the deployment target")
    return path.read_bytes()


def load_artifact(manifest_path: Path) -> tuple[dict, bytes]:
    reject_links(manifest_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict) or type(manifest.get("schema_version")) is not int or manifest["schema_version"] != 1:
        raise ValueError("Unsupported build manifest")
    validation = manifest.get("validation")
    if not isinstance(validation, dict) or any(validation.get(key) != "pass" for key in ["compile", "inspection"]):
        raise ValueError("Deployment requires successful compilation and inspection")
    if manifest.get("working_tree_dirty") is not False or manifest.get("repeated_build_identical") is not True:
        raise ValueError("Deployment requires a clean, reproducible build")
    if re.fullmatch(r"[0-9a-f]{40}", str(manifest.get("source_commit"))) is None:
        raise ValueError("Build manifest must identify its source commit")
    profile = manifest.get("build_profile", "observer")
    if profile not in ("observer", "manual-test") or manifest.get("diagnostics_default_enabled", False) is not (profile == "manual-test"):
        raise ValueError("Build profile and diagnostic defaults do not match")
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list) or len(artifacts) != 1 or not isinstance(artifacts[0], dict):
        raise ValueError("This deployment tool accepts exactly one probe artifact")
    item = artifacts[0]
    if item.get("path") != ARTIFACT_NAME or item.get("install_path") != INSTALL_PATH:
        raise ValueError("Manifest attempts to deploy outside the probe allowlist")
    artifact = safe_child(manifest_path.resolve().parent, item["path"])
    data = snapshot(artifact)
    if data is None or type(item.get("bytes")) is not int or len(data) != item["bytes"] or digest(data) != item.get("sha256"):
        raise ValueError("Artifact size or SHA-256 does not match the manifest")
    validate_gsc(data)
    return manifest, data


def ensure_game_stopped() -> None:
    if sys.platform != "win32":
        raise RuntimeError("Live deployment requires Windows process verification")
    result = subprocess.run(
        ["tasklist", "/FO", "CSV", "/NH"], capture_output=True,
        text=True, errors="replace", check=True, timeout=15,
    )
    rows = list(csv.reader(io.StringIO(result.stdout)))
    if not rows or not any(len(row) >= 2 and row[1].isdigit() for row in rows):
        raise RuntimeError("Could not verify the Windows process inventory")
    running = sorted({row[0] for row in rows if row and row[0].casefold() in GAME_PROCESSES})
    if running:
        raise RuntimeError("Close the game and launcher before deployment: " + ", ".join(running))


def atomic_write(path: Path, data: bytes) -> None:
    reject_links(path)
    descriptor, pending = tempfile.mkstemp(prefix=".hbot-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        reject_links(path)
        os.replace(pending, path)
    finally:
        if os.path.exists(pending):
            os.unlink(pending)


def write_receipt(path: Path, receipt: dict) -> None:
    atomic_write(path, (json.dumps(receipt, indent=2) + "\n").encode("utf-8"))


@contextmanager
def game_lock(root: Path):
    path = safe_child(root, ".hbot-deploy.lock")
    token = uuid.uuid4().hex
    try:
        with path.open("x", encoding="ascii") as stream:
            stream.write(token)
    except FileExistsError as exc:
        raise RuntimeError("Another deployment holds the lock; inspect a stale lock before removing it") from exc
    try:
        yield
    finally:
        reject_links(path)
        if path.is_file() and path.read_text(encoding="ascii") == token:
            path.unlink()


def plan(manifest_path: Path, game_root: Path) -> dict:
    manifest, payload = load_artifact(manifest_path)
    root = validate_game_root(game_root)
    original = snapshot(safe_child(root, INSTALL_PATH))
    action = "already_present" if original == payload else "install" if original is None else "replace"
    return {
        "action": action,
        "install_path": INSTALL_PATH,
        "original_sha256": digest(original),
        "artifact_sha256": digest(payload),
        "source_commit": manifest["source_commit"],
        "build_profile": manifest.get("build_profile", "observer"),
        "diagnostics_default_enabled": manifest.get("diagnostics_default_enabled", False),
        "game_process_check": "required_at_apply",
        "runtime_validation": "not_run",
    }


def apply(
    manifest_path: Path, game_root: Path, state_dir: Path,
    guard: Callable[[], None] = ensure_game_stopped,
) -> dict:
    manifest, payload = load_artifact(manifest_path)
    root = validate_game_root(game_root)
    reject_links(state_dir)
    state = state_dir.resolve()
    if state.is_relative_to(root):
        raise ValueError("Keep deployment receipts outside the game installation")
    target = safe_child(root, INSTALL_PATH)
    guard()
    with game_lock(root):
        original = snapshot(target)
        if original == payload:
            return {"status": "already_present", "receipt": None}
        transaction = state / uuid.uuid4().hex
        transaction.mkdir(parents=True)
        if original is not None:
            atomic_write(transaction / "original.gscc", original)
        receipt = {
            "schema_version": 1,
            "kind": RECEIPT_KIND,
            "state": "prepared",
            "game_root": str(root),
            "install_path": INSTALL_PATH,
            "source_commit": manifest["source_commit"],
            "build_profile": manifest.get("build_profile", "observer"),
            "diagnostics_default_enabled": manifest.get("diagnostics_default_enabled", False),
            "original_existed": original is not None,
            "original_sha256": digest(original),
            "artifact_sha256": digest(payload),
            "runtime_validation": "not_run",
        }
        receipt_path = transaction / "receipt.json"
        write_receipt(receipt_path, receipt)
        target.parent.mkdir(parents=True, exist_ok=True)
        guard()
        if digest(snapshot(target)) != receipt["original_sha256"]:
            raise RuntimeError("Target changed during deployment; original and receipt were preserved")
        atomic_write(target, payload)
        receipt["state"] = "installed"
        write_receipt(receipt_path, receipt)
        return {"status": "installed", "receipt": str(receipt_path), "artifact_sha256": digest(payload)}


def rollback(
    receipt_path: Path, game_root: Path,
    guard: Callable[[], None] = ensure_game_stopped,
) -> dict:
    reject_links(receipt_path)
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    if not isinstance(receipt, dict) or receipt.get("kind") != RECEIPT_KIND or type(receipt.get("schema_version")) is not int or receipt["schema_version"] != 1:
        raise ValueError("Unsupported deployment receipt")
    if receipt.get("state") not in {"prepared", "installed", "rolled_back"} or receipt.get("install_path") != INSTALL_PATH:
        raise ValueError("Receipt is outside the supported probe transaction")
    if type(receipt.get("original_existed")) is not bool:
        raise ValueError("Invalid original-file state in receipt")
    for key in ["artifact_sha256", "original_sha256"]:
        value = receipt.get(key)
        if key == "original_sha256" and not receipt["original_existed"]:
            if value is not None:
                raise ValueError("Unexpected backup digest in receipt")
        elif re.fullmatch(r"[0-9a-f]{64}", str(value)) is None:
            raise ValueError("Invalid file digest in receipt")
    root = validate_game_root(game_root)
    if receipt.get("game_root") != str(root):
        raise ValueError("Receipt does not belong to this explicitly selected game root")
    target = safe_child(root, INSTALL_PATH)
    guard()
    with game_lock(root):
        if receipt["state"] == "rolled_back":
            return {"status": "already_rolled_back"}
        current = digest(snapshot(target))
        if current == receipt["original_sha256"]:
            receipt["state"] = "rolled_back"
            write_receipt(receipt_path, receipt)
            return {"status": "already_restored"}
        if current != receipt["artifact_sha256"]:
            raise RuntimeError("Installed file changed outside this transaction; rollback preserved it")
        original = None
        if receipt["original_existed"]:
            original = snapshot(safe_child(receipt_path.resolve().parent, "original.gscc"))
            if original is None or digest(original) != receipt["original_sha256"]:
                raise ValueError("Original backup is missing or its SHA-256 changed")
        guard()
        if digest(snapshot(target)) != receipt["artifact_sha256"]:
            raise RuntimeError("Installed file changed during rollback; it was preserved")
        if original is None:
            target.unlink()
        else:
            atomic_write(target, original)
        receipt["state"] = "rolled_back"
        write_receipt(receipt_path, receipt)
        return {"status": "rolled_back", "restored_original": original is not None}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ["plan", "apply", "rollback"]:
        command = commands.add_parser(name)
        command.add_argument("--game-root", type=Path, required=True)
        if name == "rollback":
            command.add_argument("--receipt", type=Path, required=True)
        else:
            command.add_argument("--manifest", type=Path, default=ROOT / "dist" / "manifest.json")
            if name == "apply":
                command.add_argument("--state-dir", type=Path, default=ROOT / ".local" / "deployments")
    args = parser.parse_args()
    try:
        if args.command == "plan":
            result = plan(args.manifest, args.game_root)
        elif args.command == "apply":
            result = apply(args.manifest, args.game_root, args.state_dir)
        else:
            result = rollback(args.receipt, args.game_root)
    except (ValueError, OSError, RuntimeError, subprocess.SubprocessError) as exc:
        print(f"Deployment refused: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
