# Project instructions

## Product and repository scope

- Build original GSC behavior for locally hosted custom matches on MWIII.
- The first supported scope is normal small-team TDM, native mode `war`, team-based, at most 12 connected entries. Unknown modes and larger lobbies must fail closed.
- Perception and memory currently run only in shadow mode. Do not claim bot behavior changes or runtime validation from reference-model tests.
- Keep runtime adapters separate from perception, memory, decision, and action ownership.
- Shadow decisions may only consume filtered memory and sampled evidence, return independent intents, and reset with observer lifecycle. Tracking is not permission to fire. Preserve `not_run` when the user defers game tests.
- Do not import proprietary game files, third-party patch payloads, or decompiled source into this repository.
- Never put a local game path, player identifier, credential, or private log in tracked files.
- Default diagnostics and experimental behavior to opt-in.
- The ordinary `observer` build keeps defaults off. Explicit `--profile manual-test` may enable observation/selftest/diagnostics in a temporary source copy only; mark this profile in the manifest and deployment receipt. It must never enable action control.

## Workflow

- Work on a short-lived `codex/` branch and open a PR against `main`.
- Keep one behavior change per PR. Update acceptance criteria and validation evidence with the change.
- Before claiming build support, run the pinned compiler and inspect its output.
- Compilation and round-trip inspection do not establish runtime compatibility.
- Record manual game checks as `not_run`, `pass`, or `fail`; never infer them from a successful launch.
- Keep binary artifacts out of Git; build output belongs in CI artifacts or local ignored directories.
- Deployment must use an explicit target and a manifest. Check game processes, back up overwritten files, and preserve unrelated assets and player settings.
- No automatic game launch, driver changes, or live process modification in build or check commands.

## Required checks

```console
python tools/check_repository.py
python -m unittest discover -s tests -v
```

Run the compiler build and inspect gate when GSC or build tooling changes. Keep all validation honest about the tested game version and mode.
