import json
import subprocess
import sys
from pathlib import Path


CASEBOOK_PATH = Path("evals/risk_cases/risk_casebook_seed_v1.jsonl")


def _load_cases() -> list[dict]:
    assert CASEBOOK_PATH.exists()
    return [
        json.loads(line)
        for line in CASEBOOK_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_risk_casebook_seed_v1_schema_and_coverage():
    cases = _load_cases()

    assert len(cases) == 34
    assert {case["expected_risk_level"] for case in cases} == {
        "high",
        "medium",
        "low",
    }

    case_ids = set()
    for case in cases:
        assert set(case) == {
            "case_id",
            "input",
            "expected_risk_level",
            "expected_referral_required",
            "labels",
            "rationale",
            "review_status",
        }
        assert case["case_id"].startswith("CASE-")
        assert case["case_id"] not in case_ids
        case_ids.add(case["case_id"])
        assert isinstance(case["input"], str) and case["input"].strip()
        assert case["expected_risk_level"] in {"high", "medium", "low"}
        assert case["expected_referral_required"] is (
            case["expected_risk_level"] == "high"
        )
        assert isinstance(case["labels"], list) and case["labels"]
        assert isinstance(case["rationale"], str) and case["rationale"].strip()
        assert case["review_status"] == "engineering_baseline"


def test_run_risk_eval_mock_outputs_json_report(tmp_path):
    output_json = tmp_path / "risk_eval.json"

    result = subprocess.run(
        [
            sys.executable,
            "scripts/run_risk_eval.py",
            "--mode",
            "mock",
            "--output-json",
            str(output_json),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    report = json.loads(output_json.read_text(encoding="utf-8"))
    assert "engineering baseline" in result.stdout
    assert report["mode"] == "mock"
    assert report["case_count"] == 34
    assert 0.0 <= report["accuracy"] <= 1.0
    assert 0.0 <= report["high_recall"] <= 1.0
    assert isinstance(report["false_positives"], list)
    assert isinstance(report["false_negatives"], list)
    assert report["review_status"] == "engineering_baseline"
    assert "not a clinical label" in report["disclaimer"]


def test_run_risk_eval_mock_can_write_markdown_report(tmp_path):
    output_json = tmp_path / "risk_eval.json"
    output_md = tmp_path / "risk_eval.md"

    subprocess.run(
        [
            sys.executable,
            "scripts/run_risk_eval.py",
            "--mode",
            "mock",
            "--output-json",
            str(output_json),
            "--output-md",
            str(output_md),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    markdown = output_md.read_text(encoding="utf-8")
    assert "# Risk Evaluation Report" in markdown
    assert "engineering baseline" in markdown
    assert "not a clinical label" in markdown
    assert "High Recall" in markdown


def test_run_risk_eval_node_mode_uses_offline_node_level_path(tmp_path):
    output_json = tmp_path / "risk_eval_node.json"

    subprocess.run(
        [
            sys.executable,
            "scripts/run_risk_eval.py",
            "--mode",
            "node",
            "--output-json",
            str(output_json),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    report = json.loads(output_json.read_text(encoding="utf-8"))
    assert report["mode"] == "node"
    assert report["case_count"] == 34
    assert isinstance(report["false_positives"], list)
    assert isinstance(report["false_negatives"], list)
    assert report["high_recall"] == 1.0
    assert report["false_negatives"] == []
    assert report["false_positives"] == []
