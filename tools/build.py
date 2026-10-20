"""Compile original GSC twice, inspect it, and write a provenance manifest."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import struct
import subprocess
import tempfile

from tools.toolchain import ROOT, default_compiler, load_lock, sha256, verify_compiler
from tools.generate_contracts import FIXTURE, generate_file


MAGIC = bytes.fromhex("8b4753430d0a0000")
SOURCE_DIRECTORY = Path("src/hbot")
SCRIPT_NAME = "scripts/mp/hbot_probe.gsc"


def validate_gsc(data: bytes) -> None:
    if len(data) < 0x60 or data[:8] != MAGIC:
        raise ValueError("Expected a MWIII 8B GSC object")
    code_start, code_size = struct.unpack_from("<II", data, 0x34)
    declared_size = struct.unpack_from("<I", data, 0x48)[0]
    if declared_size != len(data):
        raise ValueError("Unexpected trailing data or truncated GSC object")
    if code_start < 0x60 or code_size == 0 or code_start + code_size > declared_size:
        raise ValueError("GSC code section is outside the object")


def validate_inspection(text: str) -> None:
    required = [
        r"#namespace hbot_probe;",
        r"// Namespace hbot_probe / hbot_probe",
        r"function autoexec __init__system__\(\)",
        r"function observe_match\(\)",
        r"#namespace hbot_memory;",
        r"#namespace hbot_mode;",
        r"#namespace hbot_perception;",
        r"#namespace hbot_contracts;",
        r"#namespace hbot_diagnostics;",
        r"hbot_mode::supports_tdm\(",
        r"hbot_memory::record_visible\(",
        r'getdvarint\( @"hbot_memory_enabled", 0 \)',
        r'getdvarint\( @"hbot_memory_selftest", 0 \)',
        r'getdvarint\( @"hbot_probe_enabled", 0 \)',
        r'getdvarint\( @"hbot_debug_enabled", 0 \)',
        r'level endon\( "game_ended" \)',
        r"// dev strs \.\. 0\s",
    ]
    for pattern in required:
        if re.search(pattern, text) is None:
            raise ValueError(f"Compiled probe failed inspection: {pattern}")
    forbidden = re.compile(
        r"\b(?:botpressbutton|botsetscriptgoal|botsetscriptenemy|setorigin|"
        r"setplayerangles|setweaponammostock|setweaponammoclip|setdvar|"
        r"takeallweapons|giveweapon)\s*\(", re.IGNORECASE,
    )
    if forbidden.search(text):
        raise ValueError("Observational probe contains a behavior-changing call")
    if re.search(r"\bfunction_[0-9a-f]{8,}\b|<dev string>|Unknown opcode|BAD OP", text):
        raise ValueError("Probe contains unresolved calls or unsupported output")


def run(executable: Path, arguments: list[str]) -> str:
    completed = subprocess.run(
        [str(executable), "--noUpdater", "--seed", str(load_lock()["random_seed"]), *arguments], cwd=ROOT,
        text=True, encoding="utf-8", errors="replace", capture_output=True,
        timeout=60, check=True,
    )
    text = completed.stdout + completed.stderr
    if "ERROR" in text:
        raise ValueError(text)
    return text


def compile_once(executable: Path, output: Path, generated: Path) -> str:
    return run(executable, [
        "gscc", "--game", "mwiii", "--platform", "pc", "--detour", "none",
        "--name", SCRIPT_NAME, "--namespace", "hbot_probe", "--output", output.relative_to(ROOT).as_posix(),
        SOURCE_DIRECTORY.as_posix(), generated.relative_to(ROOT).as_posix(),
    ])


def validate_memory_source(source: str) -> None:
    code = re.sub(r"//[^\n]*", "", source)
    if re.search(r"\b(?:level|self|gettime|geteye|getplayerangles|sighttracepassed|isplayer|isbot|getentitynumber)\b", code):
        raise ValueError("Memory domain must not read runtime entities or engine state")


def validate_diagnostics_source(source: str) -> None:
    code = re.sub(r"//[^\n]*", "", source)
    if re.search(r"\b(?:origin|geteye|getplayerangles|sighttracepassed|sample_visible|record_visible)\b", code):
        raise ValueError("Diagnostics must not read world positions, resample, or write observations")


def git_value(*arguments: str) -> str:
    return subprocess.check_output(
        ["git", *arguments], cwd=ROOT, text=True, encoding="utf-8",
    ).strip()


def build(executable: Path) -> dict:
    verify_compiler(executable)
    build_root = ROOT / "build"
    build_root.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="probe-", dir=build_root) as stage_name:
        stage = Path(stage_name)
        generated = stage / "contracts.gsc"
        generated_source = generate_file(ROOT, generated)
        sources = sorted((ROOT / SOURCE_DIRECTORY).glob("*.gsc"))
        validate_memory_source((ROOT / SOURCE_DIRECTORY / "memory.gsc").read_text(encoding="utf-8"))
        validate_diagnostics_source((ROOT / SOURCE_DIRECTORY / "diagnostics.gsc").read_text(encoding="utf-8"))
        first = stage / "first" / "hbot_probe"
        second = stage / "second" / "hbot_probe"
        logs = compile_once(executable, first, generated) + compile_once(executable, second, generated)
        artifact = first.with_suffix(".gscc")
        validate_gsc(artifact.read_bytes())
        if sha256(artifact) != sha256(second.with_suffix(".gscc")):
            raise ValueError("Repeated compilation produced different bytecode")
        dictionary = stage / "names.txt"
        source = "\n".join(p.read_text(encoding="utf-8") for p in sources) + "\n" + generated_source
        names = set(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", source))
        names.add(SCRIPT_NAME)
        dictionary.write_text("\n".join(sorted(names)) + "\n", encoding="utf-8")
        inspect_dir = stage / "inspection"
        logs += run(executable, [
            "-s", dictionary.relative_to(ROOT).as_posix(), "gscinfo", "-g", "-H",
            "--vm", "jup", "--path-output", "--output", inspect_dir.relative_to(ROOT).as_posix(),
            artifact.relative_to(ROOT).as_posix(),
        ])
        inspected = inspect_dir / "hbot_probe.gsc"
        inspection = inspected.read_text(encoding="utf-8")
        validate_inspection(inspection)
        inputs = {p.relative_to(ROOT).as_posix(): sha256(p) for p in sources}
        inputs[FIXTURE.as_posix()] = sha256(ROOT / FIXTURE)
        inputs["tools/generate_contracts.py"] = sha256(ROOT / "tools/generate_contracts.py")
        source_digest = hashlib.sha256(json.dumps(inputs, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        manifest = {
            "schema_version": 1,
            "source_commit": git_value("rev-parse", "HEAD"),
            "working_tree_dirty": bool(git_value("status", "--porcelain")),
            "source_sha256": source_digest,
            "source_inputs": inputs,
            "toolchain_version": load_lock()["version"],
            "toolchain_lock_sha256": sha256(ROOT / "toolchain.lock.json"),
            "repeated_build_identical": True,
            "validation": {"compile": "pass", "inspection": "pass", "native_memory_contracts": "not_run", "game_load": "not_run", "behavior": "not_run"},
            "artifacts": [{
                "path": "hbot_probe.gscc",
                "install_path": "jupiter/Assets/Scripts/mp/hbot_probe.gscc",
                "bytes": artifact.stat().st_size,
                "sha256": sha256(artifact),
            }],
        }
        destination = ROOT / "dist"
        destination.mkdir(exist_ok=True)
        shutil.copyfile(artifact, destination / "hbot_probe.gscc")
        (destination / "hbot_probe.inspection.gsc.txt").write_text(inspection, encoding="utf-8")
        (destination / "build-output.txt").write_text(logs, encoding="utf-8")
        (destination / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--acts", type=Path, default=default_compiler())
    args = parser.parse_args()
    result = build(args.acts.resolve())
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
