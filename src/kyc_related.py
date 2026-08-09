"""Детерминированное извлечение связанных сторон из KYC-досье (по действующему досье
каждого заёмщика). Порог голосующих прав берётся из самого досье (свой у каждого).
Связанные = доля >= порога. Результат дописывается в cache/enrichment_hidden/<sc>.json,
НЕ затирая уже записанные LLM-категории.

Запуск: HALYK_DATA=agentic-bank-hidden HALYK_ENRICH=cache/enrichment_hidden python3 -m src.kyc_related
"""
from __future__ import annotations
import os, re, json, csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / os.environ.get("HALYK_DATA", "agentic-bank-hidden")
ENRICH = ROOT / os.environ.get("HALYK_ENRICH", "cache/enrichment_hidden")
SD = "/private/tmp/claude-501/-Users-hubtech-Documents-halyk-bank-ai-agency/3ac569a4-3ca1-4299-800d-cd56f54c1466/scratchpad/hidden"


def sc2acc() -> dict:
    m = {}
    for r in csv.DictReader(open(DATA / "master_ledger_2025.csv")):
        s = r["txn_id"].split("-")[1]
        if not s.startswith("9"):
            m.setdefault(s, r["account_id"])
    return m


def current_kyc(acc: str) -> str | None:
    for fn in os.listdir(SD):
        t = open(os.path.join(SD, fn), errors="ignore").read()
        if "Доля голосующих прав" not in t or acc not in t:
            continue
        low = t.lower()
        if "недействующ" in low or "предыдущая редакц" in low:
            continue
        return t
    return None


def parse_related(t: str) -> tuple[list[str], float]:
    rows = re.findall(r'^\s*["“]?([A-ZА-Я][^\n%]+?)\s{2,}(\d{1,2}\.\d)%', t, re.M)
    m = re.search(r"(\d{1,2}[\.,]\d)\s*%?\s*и более", t)
    thr = float(m.group(1).replace(",", ".")) if m else 20.0
    rel = []
    for name, pct in rows:
        if float(pct) >= thr:
            core = re.sub(r'["“”]', "", name)                       # убрать любые кавычки
            core = re.sub(r"[.,]?\s*(LLP|JSC|LLC|B\.V\.|L\.?L\.?P\.?)\.?\s*$", "", core, flags=re.I)
            core = core.strip().rstrip(".,").strip()
            if core:
                rel.append(core)
    return rel, thr


def main():
    m = sc2acc()
    done = 0
    for sc, acc in sorted(m.items()):
        t = current_kyc(acc)
        if not t:
            continue
        rel, thr = parse_related(t)
        p = ENRICH / f"{sc}.json"
        obj = json.loads(p.read_text()) if p.exists() else {}
        obj["related_parties"] = rel
        obj["_related_parties_source"] = f"KYC {acc}, порог >={thr}%"
        p.write_text(json.dumps(obj, ensure_ascii=False, indent=2))
        print(f"{sc} ({acc}) thr>={thr}%: {rel}")
        done += 1
    print(f"\nсвязанные стороны заполнены для {done} сценариев")


if __name__ == "__main__":
    main()
