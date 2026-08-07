"""LLM-слой извлечения: классификация каждой транзакции в таксономию ковенантов.

Роль в гибридной архитектуре: описание операции в реестре сформулировано
состязательно (контрагент — шум, встречаются возвраты/ребейты/сторно). LLM читает
описание и присваивает категорию из закрытого списка; результат КЭШИРУЕТСЯ в
cache/enrichment/<sc>.json (поле "categories") и коммитится. Дальше движок считает
детерминированно — воспроизведение submission НЕ требует ключа и сети.

Приоритет в ledger.py: аудиторские reclassifications > эти categories > keyword-fallback.
Поэтому ручные находки (реклассификации из финальных примечаний) не затираются.

Запуск:  GROQ_API_KEY=... python3 -m src.llm_extract [P7 ...]
Без аргументов обрабатывает все 12 сценариев.
"""
from __future__ import annotations
import os, sys, json, time, urllib.request
from pathlib import Path
from collections import defaultdict

from .ledger import load_ledger, ENRICH_DIR

MODEL = "llama-3.3-70b-versatile"
API = "https://api.groq.com/openai/v1/chat/completions"

TAXONOMY = """revenue  — операционная выручка от основной деятельности (продажи, оказанные услуги, throughput, tariff/handling/storage income). НЕ выручка: возвраты налогов, ребейты, возвраты переплат.
opex     — операционные расходы: обслуживание, эксплуатация, консалтинг/advisory/retainer, клининг, охрана, курьер, канцтовары, униформа, юруслуги, вывоз отходов.
marketing— маркетинг и реклама: media buy, radio/digital ad, рекламные кампании, спонсорство, брендинг, выставки, полиграфия/collateral, newsletter. (Отдельно от opex.)
capex    — капитальные затраты: покупка/приобретение/передача оборудования, машин, основных средств, строительство, установка ОС.
rent     — аренда/лизинг помещений, площадок, оборудования, парковок, крыш.
payroll  — оплата труда: зарплата, премии, надбавки, выходные пособия, расчёты с персоналом.
utilities— коммунальные и связь: электричество, вода, отопление, газ, компрессорный воздух, телеком/мобильная связь, интернет.
taxes    — налоги и обязательные платежи: НДС, акциз, налог на имущество/добычу, пошлины, штрафы/пени налоговые.
interest — проценты: по кредитам, овердрафту, купоны, дефолтные проценты, проценты по кредитным линиям.
insurance— страхование: страховые премии, полисы, страховые возвраты.
financing_inflows — привлечённое финансирование: выборка кредита/транша, drawdown, эмиссия облигаций, взнос в капитал.

Правило: классифицируй по ПРИРОДЕ операции, независимо от знака суммы (возврат аренды = rent, ребейт по зарплате = payroll). Контрагент игнорируй — это шум."""

SYS = ("Ты финансовый аналитик. Классифицируй каждую операцию строго в одну категорию из списка. "
       "Верни ТОЛЬКО JSON-объект вида {\"TXN-...\": \"category\", ...} без пояснений.\n\nКАТЕГОРИИ:\n" + TAXONOMY)


def _call(payload: dict) -> str:
    key = os.environ["GROQ_API_KEY"]
    req = urllib.request.Request(API, data=json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json",
                 "User-Agent": "curl/8.0"})
    for attempt in range(6):
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return json.loads(r.read())["choices"][0]["message"]["content"]
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < 5:
                time.sleep(20 * (attempt + 1))  # бэкофф на лимит запросов
                continue
            raise


def classify_scenario(sc: str, txns: list) -> dict:
    items = [{"txn_id": t.txn_id, "description": t.description} for t in txns if t.scenario == sc]
    user = "Операции:\n" + "\n".join(f'{it["txn_id"]}: {it["description"]}' for it in items)
    payload = {"model": MODEL, "temperature": 0, "response_format": {"type": "json_object"},
               "messages": [{"role": "system", "content": SYS}, {"role": "user", "content": user}]}
    out = _call(payload)
    data = json.loads(out)
    valid = {"revenue","opex","marketing","capex","rent","payroll","utilities","taxes","interest","insurance","financing_inflows"}
    return {k: v for k, v in data.items() if v in valid and k.startswith("TXN-")}


def main():
    scs = sys.argv[1:] or ["B1","B4"] + [f"P{i}" for i in range(1, 11)]
    txns = load_ledger()
    for sc in scs:
        cats = classify_scenario(sc, txns)
        p = ENRICH_DIR / f"{sc}.json"
        obj = json.loads(p.read_text()) if p.exists() else {}
        obj["categories"] = cats
        obj["_categories_source"] = f"LLM {MODEL} (кэш, воспроизводимо без ключа)"
        p.write_text(json.dumps(obj, ensure_ascii=False, indent=2))
        print(f"{sc}: {len(cats)} операций классифицировано")
        time.sleep(1)


if __name__ == "__main__":
    main()
