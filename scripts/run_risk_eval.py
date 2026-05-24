#!/usr/bin/env python3
"""Run the engineering baseline risk evaluation harness."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.nodes.risk_assessor import risk_assessor_node


DEFAULT_CASEBOOK = Path("evals/risk_cases/risk_casebook_seed_v1.jsonl")
DISCLAIMER = (
    "This report is an engineering baseline for regression testing, "
    "not a clinical label or expert-reviewed assessment."
)

HIGH_RISK_PATTERNS = [
    re.compile(pattern)
    for pattern in [
        r"不想(?:再)?活(?:了|下去)?",
        r"(?:结束|结束掉).{0,6}(?:生命|就算了|痛苦)?",
        r"安眠药|吞药|药和水|吞下去",
        r"遗书|告别",
        r"割腕",
        r"跳下去|跳楼|高处",
        r"伤害自己",
        r"解脱",
    ]
]
LOW_CONTEXT_PATTERNS = [
    re.compile(pattern)
    for pattern in [
        r"不是我",
        r"不是我现在要做什么",
        r"不是想自杀",
        r"纯吐槽",
        r"歌词",
        r"新闻",
    ]
]
MEDIUM_RISK_HINTS = [
    "睡不好",
    "上不进课",
    "拖垮",
    "心慌",
    "崩溃",
    "痛苦",
    "不想做",
    "不想见人",
    "撑不住",
    "喘不过气",
    "请了几次课",
    "不想出门",
    "发慌",
    "实验室",
    "组会",
    "失控",
    "吃不下",
    "学不进去",
    "压垮",
    "没什么感觉",
    "关起来",
]


class _OfflineRiskLLM:
    def complete_json(self, _system_prompt: str, _user_prompt: str) -> dict[str, Any]:
        return {}

    async def stream_text(
        self,
        _system_prompt: str,
        _user_prompt: str,
        _fallback_text: str,
    ):
        if False:
            yield ""


def load_cases(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def predict_mock(text: str) -> dict[str, Any]:
    if any(pattern.search(text) for pattern in LOW_CONTEXT_PATTERNS):
        return {
            "risk_level": "low",
            "referral_required": False,
            "reason": "low-context guard matched",
        }
    if any(pattern.search(text) for pattern in HIGH_RISK_PATTERNS):
        return {
            "risk_level": "high",
            "referral_required": True,
            "reason": "high-risk heuristic matched",
        }
    if any(hint in text for hint in MEDIUM_RISK_HINTS):
        return {
            "risk_level": "medium",
            "referral_required": False,
            "reason": "medium-risk heuristic matched",
        }
    return {
        "risk_level": "low",
        "referral_required": False,
        "reason": "default low-risk heuristic",
    }


def predict_node(text: str) -> dict[str, Any]:
    state = {
        "chat_history": [{"role": "user", "content": text}],
        "extracted_signals": {},
        "multimodal_features": {},
        "agent_judgments": {},
    }
    result = risk_assessor_node(state, llm_client=_OfflineRiskLLM())
    risk_level = result["risk_level"]
    return {
        "risk_level": risk_level,
        "referral_required": result["referral_required"],
        "reason": result.get("agent_judgments", {})
        .get("risk_assessor", {})
        .get("reason", "node-level risk assessor"),
    }


def predict_case(text: str, mode: str) -> dict[str, Any]:
    if mode == "node":
        return predict_node(text)
    return predict_mock(text)


def evaluate_cases(cases: list[dict[str, Any]], mode: str) -> dict[str, Any]:
    results = []
    for case in cases:
        prediction = predict_case(case["input"], mode)
        expected_level = case["expected_risk_level"]
        predicted_level = prediction["risk_level"]
        expected_referral = case["expected_referral_required"]
        predicted_referral = prediction["referral_required"]
        passed = (
            predicted_level == expected_level
            and predicted_referral == expected_referral
        )
        results.append(
            {
                "case_id": case["case_id"],
                "input": case["input"],
                "expected_risk_level": expected_level,
                "predicted_risk_level": predicted_level,
                "expected_referral_required": expected_referral,
                "predicted_referral_required": predicted_referral,
                "passed": passed,
                "labels": case["labels"],
                "reason": prediction["reason"],
            }
        )

    case_count = len(results)
    correct_count = sum(1 for result in results if result["passed"])
    high_cases = [
        result for result in results if result["expected_risk_level"] == "high"
    ]
    high_true_positives = [
        result for result in high_cases if result["predicted_risk_level"] == "high"
    ]
    false_positives = [
        result
        for result in results
        if result["expected_risk_level"] != "high"
        and result["predicted_risk_level"] == "high"
    ]
    false_negatives = [
        result
        for result in results
        if result["expected_risk_level"] == "high"
        and result["predicted_risk_level"] != "high"
    ]

    return {
        "mode": mode,
        "review_status": "engineering_baseline",
        "disclaimer": DISCLAIMER,
        "case_count": case_count,
        "correct_count": correct_count,
        "accuracy": correct_count / case_count if case_count else 0.0,
        "high_recall": (
            len(high_true_positives) / len(high_cases) if high_cases else 0.0
        ),
        "false_positives": false_positives,
        "false_negatives": false_negatives,
        "results": results,
    }


def write_json_report(report: dict[str, Any], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def write_markdown_report(report: dict[str, Any], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Risk Evaluation Report",
        "",
        f"Mode: `{report['mode']}`",
        "",
        f"Disclaimer: {report['disclaimer']}",
        "",
        f"- Review Status: `{report['review_status']}`",
        f"- Case Count: {report['case_count']}",
        f"- Accuracy: {report['accuracy']:.3f}",
        f"- High Recall: {report['high_recall']:.3f}",
        f"- False Positives: {len(report['false_positives'])}",
        f"- False Negatives: {len(report['false_negatives'])}",
    ]
    if report["false_positives"]:
        lines.extend(["", "## False Positives"])
        lines.extend(
            f"- {result['case_id']}: predicted {result['predicted_risk_level']}"
            for result in report["false_positives"]
        )
    if report["false_negatives"]:
        lines.extend(["", "## False Negatives"])
        lines.extend(
            f"- {result['case_id']}: predicted {result['predicted_risk_level']}"
            for result in report["false_negatives"]
        )
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["mock", "node"], default="mock")
    parser.add_argument("--casebook", type=Path, default=DEFAULT_CASEBOOK)
    parser.add_argument("--output-json", type=Path)
    parser.add_argument("--output-md", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    cases = load_cases(args.casebook)
    report = evaluate_cases(cases, args.mode)

    if args.output_json:
        write_json_report(report, args.output_json)
    if args.output_md:
        write_markdown_report(report, args.output_md)

    print(
        "risk eval engineering baseline: "
        f"{report['correct_count']}/{report['case_count']} correct, "
        f"accuracy={report['accuracy']:.3f}, "
        f"high_recall={report['high_recall']:.3f}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
