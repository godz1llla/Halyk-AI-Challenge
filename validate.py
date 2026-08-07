"""Диагностика: сверяет вычисленные actual/status с ground_truth по всем 36 ячейкам.
Печатает относительную ошибку actual и совпадение статуса. НЕ используется в сабмите —
только для отладки логики (ground_truth в реальном скоринге скрыт)."""
import json
from pathlib import Path
from src.build_submission import build

ROOT = Path(__file__).resolve().parent
gt = json.load(open(ROOT / "data" / "ground_truth.json"))["scenarios"]
sub = build()["answers"]

st_ok = 0
n = 0
rows = []
for sc in gt:
    for cov in ("6.1", "6.2", "6.3"):
        g = gt[sc]["covenants"][cov]
        s = sub[sc][cov]
        n += 1
        smatch = g["status"] == s["status"]
        st_ok += smatch
        ga, sa = g["actual"], s["actual"]
        err = abs(sa - ga) / abs(ga) if ga else (0 if sa == 0 else 1)
        rows.append((sc, cov, smatch, ga, sa, err, g["status"], s["status"]))

for sc, cov, smatch, ga, sa, err, gs, ss in rows:
    flag = "OK " if smatch else "XX "
    aflag = "  " if err < 0.05 else "!!"
    print(f"{flag}{sc:>3} {cov}  GT={ga:>14,.2f}  ME={sa:>14,.2f}  err={err*100:6.1f}% {aflag}  {gs}/{ss}")

print(f"\nСТАТУС верных: {st_ok}/{n} = {st_ok/n*100:.1f}%")
