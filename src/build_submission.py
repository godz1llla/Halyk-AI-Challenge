"""Собирает submission.json: прогоняет движок по всем 12 сценариям × 3 ковенанта.

Запуск:  python -m src.build_submission
Результат пишется в submission.json (корень репо) по схеме submission_template.json.
"""
from __future__ import annotations
import json
from pathlib import Path

from .ledger import load_ledger, load_enrichment, scenario_txns
from .engine import evaluate

import os
ROOT = Path(__file__).resolve().parents[1]
SPECS = json.loads((ROOT / os.environ.get("HALYK_SPECS", "specs/covenants.json")).read_text())
DATA = ROOT / os.environ.get("HALYK_DATA", "data")
TEMPLATE = json.loads((DATA / "submission_template.json").read_text())
OUT = ROOT / os.environ.get("HALYK_OUT", "submission.json")

TEAM = {"team": "hubtech.kz", "contact_email": "orinbekov05@gmail.com", "model": "llama-3.3-70b + deterministic engine"}


def build() -> dict:
    all_txns = load_ledger()
    answers: dict[str, dict] = {}
    for sc, sc_spec in SPECS["scenarios"].items():
        enrich = load_enrichment(sc)
        txns = scenario_txns(all_txns, sc, enrich)
        scalars = enrich.get("scalars", {})
        evid = enrich.get("evidence", {})
        answers[sc] = {}
        for cov in ("6.1", "6.2", "6.3"):
            answers[sc][cov] = evaluate(sc_spec[cov], txns, scalars, evid.get(cov))
    return {**TEAM, "answers": answers}


if __name__ == "__main__":
    sub = build()
    OUT.write_text(json.dumps(sub, ensure_ascii=False, indent=2))
    print(f"написано {OUT} ({len(sub['answers'])} сценариев)")
