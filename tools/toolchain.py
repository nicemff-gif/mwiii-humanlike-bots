"""Install and verify the pinned external compiler without publishing its payload."""
import hashlib
import json
from pathlib import Path, PurePosixPath
import stat
import urllib.request
import zipfile


ROOT = Path(__file__).resolve().parents[1]


def load_lock() -> dict:
    return json.loads((ROOT / "toolchain.lock.json").read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def default_compiler() -> Path:
    version = load_lock()["version"]
    return ROOT / ".tools" / f"acts-{version}" / "acts" / "bin" / "acts.exe"


def verify_compiler(executable: Path) -> None:
    lock = load_lock()
    if executable.name.lower() != "acts.exe":
        raise ValueError("Compiler must be the pinned acts.exe")
    for name, expected in lock["verified_files"].items():
        path = executable.parent / name
        if not path.is_file() or sha256(path) != expected:
            raise ValueError(f"Toolchain verification failed: {name}")


def archive_path(member: zipfile.ZipInfo) -> PurePosixPath:
    if "\\" in member.filename or ":" in member.filename:
        raise ValueError("Unsupported archive path")
    path = PurePosixPath(member.filename)
    if path.is_absolute() or ".." in path.parts or not path.parts or path.parts[0] != "acts":
        raise ValueError("Archive entry escapes the acts directory")
    if stat.S_ISLNK(member.external_attr >> 16):
        raise ValueError("Archive symbolic links are not allowed")
    return path


def install() -> Path:
    lock = load_lock()
    executable = default_compiler()
    if executable.is_file():
        verify_compiler(executable)
        return executable
    cache = ROOT / ".tools"
    cache.mkdir(exist_ok=True)
    archive = cache / f"acts-{lock['version']}.zip"
    if not archive.is_file() or sha256(archive) != lock["archive_sha256"]:
        pending = archive.with_suffix(".download")
        with urllib.request.urlopen(lock["archive_url"], timeout=60) as response:
            with pending.open("wb") as output:
                while block := response.read(1024 * 1024):
                    output.write(block)
        if sha256(pending) != lock["archive_sha256"]:
            raise ValueError("Downloaded compiler archive failed SHA-256 verification")
        pending.replace(archive)
    destination = cache / f"acts-{lock['version']}"
    destination.mkdir(exist_ok=True)
    with zipfile.ZipFile(archive) as bundle:
        for member in bundle.infolist():
            archive_path(member)
        bundle.extractall(destination)
    verify_compiler(executable)
    return executable


if __name__ == "__main__":
    print(install().relative_to(ROOT))
