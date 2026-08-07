"""Отладка: печатает суммы по категориям и состав категории для сценария.
Использование: python3 debug_cats.py P7 [category]"""
import sys
from collections import defaultdict
from src.ledger import load_ledger, load_enrichment, scenario_txns

sc = sys.argv[1]
only = sys.argv[2] if len(sys.argv) > 2 else None
txns = scenario_txns(load_ledger(), sc, load_enrichment(sc))
sums = defaultdict(float); cnt = defaultdict(int)
for t in txns:
    sums[t.category] += t.usd_amount; cnt[t.category] += 1
print(f"=== {sc}: {len(txns)} txns ===")
for c in sorted(sums, key=lambda x: -abs(sums[x])):
    print(f"  {c:20} n={cnt[c]:2}  net={sums[c]:16,.2f}  absout={sum(abs(t.usd_amount) for t in txns if t.category==c and t.usd_amount<0):14,.2f}")
if only:
    print(f"\n--- {only} txns ---")
    for t in txns:
        if t.category == only:
            print(f"  {t.txn_id} {t.usd_amount:14,.2f} {t.currency}  {t.description[:70]}")
