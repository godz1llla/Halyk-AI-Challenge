"""Метрика по официальной формуле кейса — сверка submission с ground_truth.

Балл ячейки = status(0.50) + actual(0.30, по шкале) + evidence(0.20).
  actual: 0.30 * max(0, 1 - e/0.05), e = |ваше - ключ| / |ключ|
  evidence: если ключ != null → 0.20 за точное совпадение txn_id; если ключ == null →
            0.20 убывает вместе с actual по той же шкале.
  status неверен → вся ячейка 0.
Затем ячейки взвешиваются по сложности (веса нам неизвестны — считаем невзвешенную сумму).

Запуск:  python score.py [submission.json]
"""
from __future__ import annotations
import json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
GT = json.loads((ROOT / "data" / "ground_truth.json").read_text())["scenarios"]


def actual_score(mine, key) -> float:
    if mine is None or key in (None, 0):
        return 0.0 if key not in (None, 0) else 1.0
    e = abs(float(mine) - float(key)) / abs(float(key))
    return max(0.0, 1 - e / 0.05)


def cell_score(mine: dict, key: dict) -> tuple[float, float, float]:
    if not mine or mine.get("status") not in ("COMPLIANT", "BREACH"):
        return 0.0, 0.0, 0.0
    if mine["status"] != key["status"]:
        return 0.0, 0.0, 0.0
    s_status = 0.50
    a = actual_score(mine.get("actual"), key["actual"])
    s_actual = 0.30 * a
    if key["evidence_txn_id"] is None:
        s_evidence = 0.20 * a  # убывает вместе с actual
    else:
        s_evidence = 0.20 if mine.get("evidence_txn_id") == key["evidence_txn_id"] else 0.0
    return s_status, s_actual, s_evidence


def main(path: str) -> None:
    sub = json.loads(Path(path).read_text())["answers"]
    total = 0.0
    max_total = 0.0
    print(f"{'cell':8} {'st':>4} {'act':>5} {'ev':>4} {'sum':>5}   mine / key")
    for sc in sorted(GT):
        for cov in ("6.1", "6.2", "6.3"):
            key = GT[sc]["covenants"][cov]
            mine = sub.get(sc, {}).get(cov, {})
            st, ac, ev = cell_score(mine, key)
            cell = st + ac + ev
            total += cell
            max_total += 1.0
            flag = "" if cell > 0.99 else ("  <-- STATUS" if st == 0 else "  <-- actual/ev")
            print(f"{sc+' '+cov:8} {st:.2f} {ac:.3f} {ev:.2f} {cell:.3f}"
                  f"   {mine.get('status','-')}/{key['status']} "
                  f"{mine.get('actual','-')}/{key['actual']}{flag}")
    print(f"\nИТОГО (невзвешенно): {total:.3f} / {max_total:.0f}  = {total/max_total*100:.1f}%")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else str(ROOT / "submission.json"))
