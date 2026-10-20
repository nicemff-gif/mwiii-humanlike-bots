"""Generate native assertions for the pure shadow decision scenarios."""
from pathlib import Path
import re

from tools.generate_contracts import number, vector

FIXTURE = Path("tests/fixtures/decision_scenarios.json")
STATES = {"idle", "reacting", "tracking", "searching"}
KINDS = {"none", "wait", "observe", "search"}


def generate(data: dict) -> str:
    if data.get("schema_version") != 1 or not data.get("cases"):
        raise ValueError("Unsupported or empty decision contract")
    lines = [
        "#namespace hbot_contracts;", "function run_decision_contracts()", "{",
        "    report = spawnstruct();", "    report.passed = 0;", "    report.failed = 0;",
        '    report.first_failure = "none";',
    ]
    for case in data["cases"]:
        if re.fullmatch(r"[a-z0-9-]+", case["name"]) is None or not case.get("steps"):
            raise ValueError("Expected a safe name and nonempty decision scenario")
        parameters = ", ".join(number(case.get(key, default)) for key, default in [("reaction_ms", 250), ("search_ms", 3000), ("stale_ms", 2000)])
        lines.extend([
            f"    control = hbot_decision::create_controller( {parameters} );",
            f"    memory = hbot_memory::create_memory( {number(case.get('ttl_ms', 4000))}, {number(case.get('capacity', 16))} );",
        ])
        for index, step in enumerate(case["steps"]):
            lines.append(f'    report.current_case = "{case["name"]}-{index}";')
            if step["op"] == "reset":
                lines.extend(["    hbot_decision::reset( control );", "    hbot_memory::clear( memory );"])
                continue
            now = number(step["now_ms"])
            if step["op"] == "seed":
                lines.append(f"    hbot_memory::record_visible( memory, {number(step['id'])}, {vector(step['position'])}, {now} );")
                continue
            if step["op"] != "step" or not step.get("expect"):
                raise ValueError("Decision steps need an expectation")
            lines.append("    samples = [];")
            for event in step.get("samples", []):
                if type(event["visible"]) is not bool or type(event.get("record", True)) is not bool:
                    raise ValueError("Evidence flags must be booleans")
                target = number(event["id"])
                if event["visible"] and event.get("record", True):
                    lines.append(f"    hbot_memory::record_visible( memory, {target}, {vector(event['position'])}, {now} );")
                lines.extend([
                    "    sample = spawnstruct();",
                    f"    sample.target_id = {target};", f"    sample.at_ms = {number(event.get('at_ms', step['now_ms']))};",
                    f"    sample.visible = {int(event['visible'])};", "    samples[ samples.size ] = sample;",
                ])
            lines.append(f"    intent = hbot_decision::update( control, memory, samples, {now} );")
            for key, value in step["expect"].items():
                if key in ("state", "kind"):
                    if value not in (STATES if key == "state" else KINDS):
                        raise ValueError("Unknown intent state or kind")
                    condition = f'intent.{key} == "{value}"'
                elif key == "id":
                    condition = "!isdefined( intent.target_id )" if value is None else f"intent.target_id == {number(value)}"
                elif key == "position":
                    condition = "!isdefined( intent.position )" if value is None else f"isdefined( intent.position ) && intent.position == {vector(value)}"
                elif key in ("reaction_remaining_ms", "search_remaining_ms"):
                    condition = f"intent.{key} == {number(value)}"
                else:
                    raise ValueError("Unknown intent expectation")
                lines.append(f"    check( report, {condition} );")
    lines.extend(["    return report;", "}", ""])
    return "\n".join(lines)
