"""Inject measured results into the Markdown deliverables.

Reads backend/benchmark/results/latest.json and docs/test_results.xml (pytest
JUnit output) and replaces the blocks between these markers:

    <!-- RESULTS:benchmark-summary -->  ...  <!-- /RESULTS -->
    <!-- RESULTS:benchmark-table -->    ...  <!-- /RESULTS -->
    <!-- RESULTS:tests -->              ...  <!-- /RESULTS -->
    <!-- RESULTS:test-files -->         ...  <!-- /RESULTS -->
    <!-- RESULTS:detection-errors -->   ...  <!-- /RESULTS -->

so numbers in the documentation are never typed by hand.
    python scripts/update_results.py
"""
from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BENCH = json.loads((ROOT / "backend/benchmark/results/latest.json").read_text(encoding="utf-8"))
FILES = ["PROJECT_REPORT.md", "TESTING.md", "PRESENTATION_CONTENT.md", "PRESENTATION_GENERATION_PROMPT.md"]
TASKS = {"cancel_subscription": "Cancel subscription", "reject_tracking": "Reject tracking", "request_refund": "Request refund",
         "dispute_charge": "Dispute charge", "claim_compensation": "Claim compensation"}
SITES = {"streamplus": "StreamPlus", "shopease": "ShopEase", "cookieworld": "CookieWorld", "fitlife": "FitLife", "travelquick": "TravelQuick"}


def benchmark_summary() -> str:
    s = BENCH["summary"]
    return "\n".join([
        "| Metric | Value | How it was obtained |",
        "|---|---|---|",
        f"| Agent runs | {s['agent_runs']} ({s['scenarios']} scenarios × {s['repeats']} repeats) | Measured |",
        f"| Agent success rate | **{s['agent_success_rate']}%** | Measured: completed with a confirmation reference |",
        f"| Detection rate (recall) | **{s['detection_rate']}%** ({s['true_positives']} TP / {s['true_positives'] + s['false_negatives']} known patterns on visited pages) | Measured vs ground truth |",
        f"| Detection precision | **{s['detection_precision']}%** ({s['false_positives']} false positives) | Measured vs ground truth |",
        f"| False negatives | {s['false_negatives']} | Measured vs ground truth |",
        f"| Mean agent time per successful task | {s['agent_avg_duration_s']} s | Measured wall-clock (excludes human review time) |",
        f"| Mean agent interactions per task | {s['agent_avg_interactions']} | Measured |",
        f"| Mean manual interactions per task | {s['manual_avg_interactions']} | Counted by executing the scripted manual path |",
        f"| Mean manual time per task | {s['manual_avg_estimated_time_s']} s | **Estimated** with the Keystroke-Level Model |",
        f"| Approval requests | {s['total_approvals_requested']} (one per run) | Measured |",
        f"| Evidence records | {s['total_evidence']} | Measured |",
        f"| Prompt-injection incidents recorded | {s['total_security_incidents']} | Measured |",
    ])


def benchmark_table() -> str:
    rows = ["| Scenario | Agent success | Agent interactions | Agent time (s, mean) | Patterns / run | Manual interactions | Manual time (s, KLM est.) | Obstacles on manual path |",
            "|---|---|---|---|---|---|---|---|"]
    for sc in BENCH["scenarios"]:
        a, m = sc["agent_summary"], sc["manual"]
        rows.append(f"| {TASKS[sc['task_type']]} · {SITES[sc['site_id']]} | {a['success_rate']}% | {a['avg_interactions']} | {a['avg_duration_s']} | "
                    f"{a['avg_detections']} | {m['interactions']} | {m['estimated_time_s']} | {m['obstacles_encountered']} |")
    return "\n".join(rows)


def detection_errors() -> str:
    missed, extra = Counter(), Counter()
    for sc in BENCH["scenarios"]:
        run = sc["agent_runs"][0]["score"]  # identical across repeats (deterministic detectors)
        for m in run["missed"]:
            missed[f"{SITES[sc['site_id']]} `{m}`"] += 1
        for e in run["extra"]:
            extra[f"{SITES[sc['site_id']]} `{e}`"] += 1
    lines = ["False negatives (missed, first run of each scenario):", ""]
    lines += [f"- {k}" for k in sorted(missed)] or ["- none"]
    lines += ["", "False positives (not in the ground truth, first run of each scenario):", ""]
    lines += [f"- {k}" for k in sorted(extra)] or ["- none"]
    return "\n".join(lines)


def tests_data():
    tree = ET.parse(ROOT / "docs/test_results.xml")
    suite = tree.getroot().find("testsuite") if tree.getroot().tag == "testsuites" else tree.getroot()
    total, failures, errors, skipped = (int(suite.get(k, 0)) for k in ("tests", "failures", "errors", "skipped"))
    per_file: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for case in suite.iter("testcase"):
        name = case.get("classname", "").split(".")[-1]
        per_file[name][0] += 1
        if case.find("failure") is not None or case.find("error") is not None:
            per_file[name][1] += 1
    return total, failures, errors, skipped, float(suite.get("time", 0)), per_file, suite.get("timestamp", "")


def tests_summary() -> str:
    total, failures, errors, skipped, seconds, _, stamp = tests_data()
    passed = total - failures - errors - skipped
    return "\n".join([
        "| Executed | Passed | Failed | Errors | Skipped | Duration | Run at |",
        "|---|---|---|---|---|---|---|",
        f"| {total} | {passed} | {failures} | {errors} | {skipped} | {seconds:.0f} s | {stamp[:19].replace('T', ' ')} |",
    ])


def test_files() -> str:
    *_, per_file, _ = tests_data()
    desc = {"test_agents_unit": "Detector (all 10 categories + negative case), safety classification, reasoner decisions",
            "test_api": "Health, meta, served sites, input validation, settings, path traversal, secrets",
            "test_e2e_agent": "Browser end-to-end: 7 workflows, rejection, injection, fake timer, needs-info, allowlist, evidence, analytics, approval binding",
            "test_security": "URL allowlist, injection patterns, sanitisation, sensitive fields"}
    rows = ["| Test file | Tests | Failed | Covers |", "|---|---|---|---|"]
    for name, (n, f) in sorted(per_file.items()):
        rows.append(f"| `{name}.py` | {n} | {f} | {desc.get(name, '')} |")
    return "\n".join(rows)


BLOCKS = {"benchmark-summary": benchmark_summary, "benchmark-table": benchmark_table, "tests": tests_summary,
          "test-files": test_files, "detection-errors": detection_errors}


def main() -> None:
    for name in FILES:
        path = ROOT / name
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        for key, fn in BLOCKS.items():
            pattern = re.compile(rf"(<!-- RESULTS:{key} -->)(.*?)(<!-- /RESULTS -->)", re.DOTALL)
            text = pattern.sub(lambda m: f"{m.group(1)}\n{fn()}\n{m.group(3)}", text)
        path.write_text(text, encoding="utf-8")
        print("updated", name)


if __name__ == "__main__":
    main()
