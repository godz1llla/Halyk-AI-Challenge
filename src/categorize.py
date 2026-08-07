"""Детерминированная категоризация транзакций по тексту description.

Контрагент в леджере — намеренный шум (рандомные имена вроде «Bridgeport Tax
Advisory» на строке про маркетинг). Природа операции надёжно читается из description.
Каждая транзакция получает ровно одну категорию из закрытого списка ковенантов:
revenue / opex / capex / rent / payroll / utilities / taxes / interest /
insurance / financing_inflows. (Маркетинг, консалтинг, клининг и пр. — это opex.)

Правила упорядочены по приоритету: первое совпадение выигрывает. Приоритет важен,
потому что описания пересекаются («equipment yard lease» — это аренда, а не capex;
«interest on export credit line» — проценты, а не финансирование).

Ловушки конкретного заёмщика (реклассификации аудитора, курс EUR, связанные стороны)
приходят из cache/enrichment/<sc>.json и имеют приоритет над этим модулем.
"""
from __future__ import annotations
import re

# (категория, список подстрок-признаков). Порядок = приоритет.
_RULES: list[tuple[str, list[str]]] = [
    ("interest",   ["interest", "coupon", "overdraft"]),
    ("insurance",  ["insurance"]),
    ("taxes",      ["tax", "vat", "excise", "withholding", "levy", "duty",
                    "customs", "franchise", "royalty", "mineral extraction"]),
    ("payroll",    ["payroll", "salary", "salaries", "wage", "severance",
                    "staff cost", "personnel cost"]),
    ("rent",       ["rent", "lease", "parking garage", "rooftop"]),
    ("utilities",  ["electricity", "water supply", "district heating", "heating",
                    "utility", "telecom", "compressed air", "network capacity",
                    "mobile fleet", "gas supply", "sewage", "internet"]),
    ("capex",      ["purchase of", "acquisition of", "construction of",
                    "machinery", "plant and equipment", "capital works",
                    "capitalised", "fixed asset", "fit-out", "installation of"]),
    ("financing_inflows", ["drawdown", "loan facility", "term loan",
                    "credit facility", "bond issue", "note issuance",
                    "facility drawdown", "capital contribution", "equity injection"]),
    ("revenue",    ["sales", "revenue", "distribution settlement",
                    "services rendered", "freight", "throughput", "tariff income",
                    "storage income", "handling income"]),
    # marketing / advisory / cleaning / courier / security / maintenance / prof. fees -> opex
    ("opex",       ["marketing", "media buy", "radio ad", "advertis", "sponsorship",
                    "newsletter", "collateral", "advisory", "consult", "retainer",
                    "cleaning", "janitorial", "courier", "security", "maintenance",
                    "landscaping", "uniforms", "stationery", "office supplies",
                    "servicing", "operating costs", "waste", "printing"]),
]


def categorize(description: str) -> str:
    d = (description or "").lower()
    for cat, keys in _RULES:
        for k in keys:
            if k in d:
                return cat
    return "opex"  # значение по умолчанию: прочие операционные расходы
