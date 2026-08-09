"""LLM-извлечение спецификаций ковенантов из действующих кредитных договоров.

Читает пункты 6.1/6.2/6.3 каждого договора и выдаёт схему движка
(kind/direction/threshold/metric). Результат -> specs/covenants_hidden.json.
Устаревшие редакции («НЕДЕЙСТВУЮЩАЯ РЕДАКЦИЯ») отсеиваются.

Запуск:  GROQ_API_KEY=... HALYK_DATA=agentic-bank-hidden python3 -m src.llm_specs
"""
from __future__ import annotations
import os, re, json, time, urllib.request, csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / os.environ.get("HALYK_DATA", "agentic-bank-hidden")
SD = "/private/tmp/claude-501/-Users-hubtech-Documents-halyk-bank-ai-agency/3ac569a4-3ca1-4299-800d-cd56f54c1466/scratchpad/hidden"
MODEL = "llama-3.3-70b-versatile"

SCHEMA = """Каждый ковенант -> объект. Возможные kind и их metric:
- {"kind":"aggregate_min"|"aggregate_max","direction":"min"|"max","threshold":N,"metric":{"category":"revenue|capex|...","period_filter":"Q4"?}}
- {"kind":"ratio","direction":...,"threshold":N,"metric":{"numerator":[термы],"denominator":[термы]}}  (терм = имя категории; "-cat" = вычесть; scalar-имя допускается)
- {"kind":"related_party_abs","direction":"max","threshold":N,"metric":{"category":"related_party"}}
- {"kind":"related_party_ratio","direction":"max","threshold":N,"metric":{"numerator":["related_party"],"denominator":["revenue"|"opex"]}}
- {"kind":"max_single_line","direction":"max","threshold":N,"metric":{"lines":["payroll","utilities"]}}
- {"kind":"min_less_largest","direction":"min","threshold":N,"metric":{"base":"revenue","subtract_largest_of":["payroll","taxes"]}}
- {"kind":"springing_ratio","direction":"max","threshold":N,"metric":{"numerator":[...],"denominator":[...],"trigger":{"category":"financing_inflows","above":N}}}
- {"kind":"point_in_time_liability","direction":"max","threshold":N,"metric":{"components":["payroll","severance_program_liability"]}}

Категории: revenue, opex, capex, rent, payroll, utilities, taxes, interest, insurance, financing_inflows, marketing, related_party.
Скаляры (из аудита, не из леджера): group_capex, addbacks, severance_program_liability, transfers_to_unrestricted_subs.
EBITDA = ["revenue","-opex"]. ICR числитель EBITDA, знаменатель ["interest"]."""

SYS = ("Ты извлекаешь параметры банковских ковенантов из текста договора. "
       "Верни СТРОГО JSON {\"6.1\":{...},\"6.2\":{...},\"6.3\":{...}} по схеме. threshold — число (без $ и запятых). "
       "Коэффициенты типа 0.42x -> threshold 0.42. Без пояснений.\n\n" + SCHEMA)


def _call(user: str) -> str:
    key = os.environ["GROQ_API_KEY"]
    payload = {"model": MODEL, "temperature": 0, "response_format": {"type": "json_object"},
               "messages": [{"role": "system", "content": SYS}, {"role": "user", "content": user}]}
    req = urllib.request.Request("https://api.groq.com/openai/v1/chat/completions",
        data=json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json", "User-Agent": "curl/8.0"})
    for a in range(6):
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return json.loads(r.read())["choices"][0]["message"]["content"]
        except urllib.error.HTTPError as e:
            if e.code == 429 and a < 5:
                time.sleep(20 * (a + 1)); continue
            raise


def sc2acc() -> dict:
    m = {}
    for r in csv.DictReader(open(DATA / "master_ledger_2025.csv")):
        s = r["txn_id"].split("-")[1]
        if not s.startswith("9"):
            m.setdefault(s, r["account_id"])
    return m


def current_agreement(sc: str, acc: str) -> str | None:
    """Файл действующего договора сценария: содержит счёт и пункты 6.1, но НЕ устаревший."""
    best = None
    for fn in os.listdir(SD):
        t = open(os.path.join(SD, fn), errors="ignore").read()
        if acc not in t or "Пункт 6.1" not in t:
            continue
        low = t.lower()
        if "недействующая редакция" in low or "предыдущая редакц" in low:
            continue
        return t
    return best


def covenant_text(t: str) -> str:
    i = t.find("Пункт 6.1")
    seg = t[i:i + 3000] if i >= 0 else t[-3000:]
    # добавим определение связанной стороны/ебитда если рядом
    return seg


def main():
    m = sc2acc()
    specs = {"period": {"start": "2025-01-01", "end": "2025-12-31"}, "scenarios": {}}
    for sc in sorted(m):
        acc = m[sc]
        t = current_agreement(sc, acc)
        if not t:
            print(f"{sc}: НЕТ действующего договора ({acc})"); continue
        out = _call(f"Заёмщик {sc}, счёт {acc}. Текст ковенантов:\n\n{covenant_text(t)}")
        try:
            d = json.loads(out)
            specs["scenarios"][sc] = {"account": acc, **{k: d[k] for k in ("6.1", "6.2", "6.3") if k in d}}
            print(f"{sc}: {d['6.1']['kind']} / {d['6.2']['kind']} / {d['6.3']['kind']}")
        except Exception as e:
            print(f"{sc}: ОШИБКА разбора: {e}\n{out[:200]}")
        time.sleep(1)
    (ROOT / "specs" / "covenants_hidden.json").write_text(json.dumps(specs, ensure_ascii=False, indent=2))
    print(f"\nзаписано specs/covenants_hidden.json: {len(specs['scenarios'])} сценариев")


if __name__ == "__main__":
    main()
