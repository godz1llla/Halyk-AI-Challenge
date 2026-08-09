"""Детерминированный расчёт ковенантов.

На вход: спецификация ковенанта (specs/covenants.json) + обогащённые транзакции сценария
(ledger.scenario_txns) + скаляры из аудита. На выход: {status, actual, evidence_txn_id}.

Ключевые правила кейса:
- actual — ВСЕГДА положительное число (модуль), 2 знака. Коэффициенты — обычным числом.
- status: min → BREACH если actual < threshold; max → BREACH если actual > threshold.
- evidence_txn_id — единственная транзакция, чья переклассификация/включение/исключение
  меняет вердикт; для коэффициентных/агрегатных тестов, где вердикт не определяется одной
  строкой, ключ = null. Здесь берётся из обогащения (анализ реклассификаций).
"""
from __future__ import annotations
from .ledger import Txn


def _cat_sum(txns: list[Txn], category: str) -> float:
    """Сумма модулей usd_amount транзакций указанной категории."""
    return round(sum(abs(t.usd_amount) for t in txns if t.category == category), 2)


def _related_party_sum(txns: list[Txn]) -> float:
    # «Платежи связанным сторонам» = только оттоки (отрицательные суммы).
    # Поступления от связанной стороны (выручка, возвраты) не являются платежами.
    return round(sum(abs(t.usd_amount) for t in txns if t.related_party and t.usd_amount < 0), 2)


def _resolve_terms(terms: list[str], txns: list[Txn], scalars: dict) -> float:
    """Сумма по списку слагаемых. Элемент '-cat' вычитается; 'related_party' — спец-категория;
    имена вне ledger (group_capex, addbacks, ...) берутся из scalars."""
    total = 0.0
    for term in terms:
        if isinstance(term, (int, float)):  # константа в формуле (напр., из LLM-спека)
            total += float(term)
            continue
        neg = term.startswith("-")
        name = term[1:] if neg else term
        if name == "related_party":
            val = _related_party_sum(txns)
        elif name in scalars:
            val = float(scalars[name])
        else:
            val = _cat_sum(txns, name)
        total += -val if neg else val
    return total


def _status(actual: float, direction: str, threshold: float) -> str:
    if direction == "min":
        return "BREACH" if actual < threshold else "COMPLIANT"
    return "BREACH" if actual > threshold else "COMPLIANT"


def evaluate(spec: dict, txns: list[Txn], scalars: dict, evidence: str | None = None) -> dict:
    kind = spec["kind"]
    direction = spec["direction"]
    threshold = spec["threshold"]
    m = spec.get("metric", {})

    if kind in ("aggregate_min", "aggregate_max"):
        pool = txns
        pf = m.get("period_filter")
        if pf == "Q4":
            pool = [t for t in txns if t.date[5:7] in ("10", "11", "12")]
        actual = _cat_sum(pool, m["category"])

    elif kind == "max_single_line":
        actual = max(_cat_sum(txns, line) for line in m["lines"])

    elif kind == "min_less_largest":
        base = _cat_sum(txns, m["base"])
        actual = base - max(_cat_sum(txns, c) for c in m["subtract_largest_of"])

    elif kind == "related_party_abs":
        actual = _related_party_sum(txns)

    elif kind in ("ratio", "related_party_ratio", "springing_ratio"):
        num = _resolve_terms(m["numerator"], txns, scalars)
        den = _resolve_terms(m["denominator"], txns, scalars)
        actual = num / den if den else 0.0

    elif kind == "point_in_time_liability":
        actual = _resolve_terms(m["components"], txns, scalars)

    elif kind in ("quarterly_min", "quarterly_max"):
        # показатель считается отдельно за каждый квартал; берём худший (мин/макс).
        terms = m.get("terms") or [m.get("category", "revenue")]
        byq: dict[int, list] = {}
        for t in txns:
            byq.setdefault((int(t.date[5:7]) - 1) // 3, []).append(t)
        vals = [_resolve_terms(terms, byq.get(q, []), scalars) for q in range(4)]
        actual = min(vals) if kind == "quarterly_min" else max(vals)

    else:
        raise ValueError(f"неизвестный kind: {kind}")

    # Статус считаем по НЕокруглённому значению (иначе actual, равный порогу после
    # округления, ложно проходит тест, тогда как истинное значение его нарушает).
    raw = abs(actual)
    actual = round(raw, 2)

    # springing: тест применяется только при срабатывании условия; иначе COMPLIANT,
    # но actual всё равно = фактическое значение показателя (правило кейса).
    if kind == "springing_ratio":
        trig = spec.get("trigger") or m.get("trigger") or {}
        cat, above = trig.get("category"), trig.get("above")
        # при неполном описании триггера безопаснее применить тест, чем пропустить нарушение
        triggered = (_cat_sum(txns, cat) > above) if (cat and above is not None) else True
        status = _status(raw, direction, threshold) if triggered else "COMPLIANT"
    else:
        status = _status(raw, direction, threshold)

    return {"status": status, "actual": actual, "evidence_txn_id": evidence}
