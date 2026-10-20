"""Emit opt-in native GSC self-tests from the shared memory scenario contract."""
import json
import math
from pathlib import Path
import re


FIXTURE = Path("tests/fixtures/memory_scenarios.json")


def number(value) -> str:
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError("Contract numbers must be finite")
    return repr(value)


def vector(value) -> str:
    if value is None:
        return "undefined"
    if not isinstance(value, list) or len(value) != 3:
        raise ValueError("Contract positions must contain exactly three components")
    return "( " + ", ".join(number(n) for n in value) + " )"


def generate(data: dict) -> str:
    if data.get("schema_version") != 1 or not data.get("cases"):
        raise ValueError("Unsupported or empty scenario contract")
    lines = [
        "// Generated from the shared scenario contract; runtime execution remains opt-in.",
        "#namespace hbot_contracts;", "function run_memory_contracts()", "{",
        "    report = spawnstruct();", "    report.passed = 0;", "    report.failed = 0;",
        '    report.first_failure = "none";',
    ]
    for index, case in enumerate(data.get("mode_cases", [])):
        mode = case["mode"]
        if mode is not None and (not isinstance(mode, str) or re.fullmatch(r"[a-z_]+", mode) is None):
            raise ValueError("Mode names must be safe ASCII identifiers")
        mode_literal = "undefined" if mode is None else json.dumps(mode)
        if case["teambased"] not in (True, False, None) or type(case["allowed"]) is not bool:
            raise ValueError("Mode flags must be booleans or undefined")
        team = "undefined" if case["teambased"] is None else "1" if case["teambased"] else "0"
        expected = "1" if case["allowed"] else "0"
        lines.append(f'    report.current_case = "mode-{index}";')
        lines.append(f"    check( report, hbot_mode::supports_tdm( {mode_literal}, {team}, {number(case['count'])} ) == {expected} );")
    for case in data["cases"]:
        if re.fullmatch(r"[a-z0-9-]+", case["name"]) is None:
            raise ValueError("Scenario names must be safe ASCII slugs")
        ttl, capacity = number(case["ttl_ms"]), number(case["capacity"])
        lines.extend([f'    report.current_case = "{case["name"]}";', f"    memory = hbot_memory::create_memory( {ttl}, {capacity} );"])
        for step in case["steps"]:
            op = step["op"]
            if op == "reset":
                lines.append("    hbot_memory::clear( memory );")
                continue
            now = number(step["now_ms"])
            if op == "hidden":
                # world_position is deliberately unavailable to the memory domain.
                lines.append(f"    hbot_memory::advance( memory, {now} );")
            elif op == "see":
                target, point = number(step["id"]), vector(step["position"])
                accepted = 1 if step.get("accepted", True) else 0
                lines.append(f"    accepted = hbot_memory::record_visible( memory, {target}, {point}, {now} );")
                lines.append(f"    check( report, accepted == {accepted} );")
            elif op == "expect":
                lines.append(f"    contact = hbot_memory::recall( memory, {number(step['id'])}, {now} );")
                contact = step["contact"]
                if contact is None:
                    lines.append("    check( report, !isdefined( contact ) );")
                else:
                    point = vector(contact["position"])
                    seen, confidence = number(contact["seen_at"]), number(contact["confidence"])
                    lines.append(
                        "    check( report, isdefined( contact ) && "
                        f"contact.position == {point} && contact.seen_at == {seen} && "
                        f"abs( contact.confidence - {confidence} ) < 0.00001 );"
                    )
            else:
                raise ValueError(f"Unsupported contract operation: {op}")
    lines.extend([
        "    return report;", "}", "function check( report, condition )", "{",
        "    if ( condition )", "    {", "        report.passed++;", "    }",
        "    else", "    {", "        report.failed++;",
        '        if ( report.first_failure == "none" )', "        {",
        "            report.first_failure = report.current_case;", "        }", "    }", "}", "",
    ])
    return "\n".join(lines)


def generate_file(root: Path, destination: Path) -> str:
    data = json.loads((root / FIXTURE).read_text(encoding="utf-8"))
    generated = generate(data)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(generated, encoding="utf-8")
    return generated
