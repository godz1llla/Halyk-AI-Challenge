"""Загрузка и обогащение реестра транзакций.

Реестр (master_ledger_2025.csv) — единая таблица по всем счетам. Расходы записаны
отрицательными суммами, поступления — положительными, валюты разные (USD/EUR).

Сценарий (P1..P10, B1, B4) связан со счётом через ID транзакции: TXN-<scenario>-NNNN.
Обогащение (категория транзакции, признак связанной стороны, курс валюты, реклассификации)
поставляет слой извлечения — cache/enrichment/<scenario>.json. Пока файла нет, транзакции
возвращаются без категорий (category=None), и движок посчитает только то, что не требует
классификации.
"""
from __future__ import annotations
import csv, json, os
from dataclasses import dataclass, field
from pathlib import Path

from .categorize import categorize

ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / "data" / "master_ledger_2025.csv"
ENRICH_DIR = ROOT / "cache" / "enrichment"


@dataclass
class Txn:
    txn_id: str
    date: str
    account_id: str
    counterparty: str
    description: str
    amount: float          # исходная сумма (знак сохранён), в валюте currency
    currency: str
    # поля обогащения:
    category: str | None = None       # revenue/opex/capex/rent/payroll/utilities/taxes/interest/insurance/financing_inflows/...
    related_party: bool = False
    usd_amount: float = 0.0           # amount, конвертированный в USD (знак сохранён)

    @property
    def scenario(self) -> str:
        # TXN-P1-0039 -> P1 ; TXN-9001-0036 -> 9001 (шумовые счета)
        return self.txn_id.split("-")[1]


def load_ledger(path: Path = LEDGER) -> list[Txn]:
    rows = []
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            # Некоторые строки намеренно имеют пустую сумму (начисленные, но неуплаченные
            # налоги/обязательства) — их фактическое значение раскрыто в аудиторском отчёте
            # и подставляется через enrichment['amount_overrides']. Пока считаем 0.
            raw = (r["amount"] or "").strip()
            rows.append(Txn(
                txn_id=r["txn_id"], date=r["date"], account_id=r["account_id"],
                counterparty=r["counterparty"], description=r["description"],
                amount=float(raw) if raw else 0.0, currency=r["currency"],
            ))
    return rows


def load_enrichment(scenario: str) -> dict:
    """Читает cache/enrichment/<scenario>.json. Ожидаемая схема:
    {
      "fx_rates": {"EUR": 1.08},                 # курс валюта->USD (или per_txn: {txn_id: rate})
      "related_parties": ["Aktau Holdings"],     # подстроки имён связанных сторон (из KYC)
      "categories": {"TXN-P1-0001": "opex", ...},# категория по каждой транзакции
      "reclassifications": {"TXN-...": "interest"},  # переопределение категории аудитором
      "scalars": {"group_capex": 0, "severance_program_liability": 0, "addbacks": 0,
                  "transfers_to_unrestricted_subs": 0},
      "evidence": {"6.1": "TXN-...", ...}         # транзакция, определяющая нарушение
    }
    """
    p = ENRICH_DIR / f"{scenario}.json"
    if not p.exists():
        return {}
    return json.loads(p.read_text())


def scenario_txns(all_txns: list[Txn], scenario: str, enrich: dict) -> list[Txn]:
    """Отфильтровать транзакции сценария и применить обогащение (FX, категории, связанные стороны)."""
    fx = enrich.get("fx_rates", {})
    per_txn_fx = enrich.get("per_txn_fx", {})
    rp_names = [n.lower() for n in enrich.get("related_parties", [])]
    cats = enrich.get("categories", {})
    reclass = enrich.get("reclassifications", {})
    amount_overrides = enrich.get("amount_overrides", {})  # начисленные суммы из аудита

    out = []
    for t in all_txns:
        if t.scenario != scenario:
            continue
        if t.txn_id in amount_overrides:
            t.amount = float(amount_overrides[t.txn_id])
        # конвертация в USD
        rate = per_txn_fx.get(t.txn_id, fx.get(t.currency, 1.0 if t.currency == "USD" else None))
        t.usd_amount = t.amount * rate if rate is not None else t.amount
        # категория: реклассификация аудитора > явная категория из enrichment >
        # детерминированная категоризация по тексту description.
        t.category = reclass.get(t.txn_id) or cats.get(t.txn_id) or categorize(t.description)
        # связанная сторона
        t.related_party = any(n in t.counterparty.lower() for n in rp_names)
        out.append(t)
    return out
