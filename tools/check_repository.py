"""Check tracked publishable files without reading credentials or game folders."""
from pathlib import Path, PurePosixPath
import subprocess
import sys


FORBIDDEN_SUFFIXES = {
    ".exe", ".dll", ".sys", ".ff", ".fp", ".xpak", ".xsub", ".gscc",
    ".gscasm", ".gscgdb", ".zip", ".7z", ".rar", ".dmp", ".mdmp", ".log",
}
FORBIDDEN_NAMES = {"settings.json", "script_manager.json", ".env"}
FORBIDDEN_ROOTS = {".tools", ".local", "dist", "build", "artifacts"}


def path_problem(name: str) -> str | None:
    path = PurePosixPath(name.replace("\\", "/"))
    lowered = path.as_posix().lower()
    if path.is_absolute() or ".." in path.parts or ":" in lowered:
        return "path must stay relative to the repository"
    if path.suffix.lower() in FORBIDDEN_SUFFIXES:
        return "binary, runtime, or third-party payload"
    if path.name.lower() in FORBIDDEN_NAMES or ".local." in path.name.lower():
        return "local configuration"
    if path.parts and path.parts[0].lower() in FORBIDDEN_ROOTS:
        return "generated or local directory"
    if lowered.startswith("references/private/") or lowered.endswith(".decompiled.gsc.txt"):
        return "private reverse-engineering material"
    if path.name.startswith(".env.") and path.name != ".env.example":
        return "local environment"
    return None


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        ["git", "ls-files", "-z"], cwd=root, capture_output=True, check=True,
    )
    problems = []
    paths = result.stdout.decode("utf-8").split("\0")
    for name in filter(None, paths):
        problem = path_problem(name)
        path = root / name
        if problem:
            problems.append(f"{name}: {problem}")
        elif path.is_symlink():
            problems.append(f"{name}: symbolic links are not published")
        elif path.is_file():
            if path.stat().st_size > 1_000_000:
                problems.append(f"{name}: tracked file exceeds 1 MB")
            elif b"\0" in path.read_bytes():
                problems.append(f"{name}: binary content")
    if problems:
        print("\n".join(problems), file=sys.stderr)
        return 1
    print(f"Repository checks passed ({len(list(filter(None, paths)))} tracked files).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
