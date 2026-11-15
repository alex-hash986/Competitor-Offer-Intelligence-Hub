import re

from app.services.extractor import CTA

CRITERIA = ("uvp_clarity", "price_transparency", "cta_strength", "trust_proof", "friction_reducers")


def calculate_cro_score(extracted: dict) -> tuple[int, dict[str, int]]:
    h1 = extracted.get("h1_text", "").strip()
    sub = extracted.get("subheadline", "").strip()
    uvp = (8 if len(h1) >= 15 and len(h1.split()) >= 3 else 3 if h1 else 0)
    uvp += 8 if len(sub) >= 25 else 4 if sub else 0
    uvp += 4 if sub and re.search(r"\b\d", f"{h1} {sub}") else 0

    price_count = len(set(extracted.get("extracted_prices", [])))
    prices = 20 if price_count >= 2 else 14 if price_count else 0
    cta = {label.casefold() for label in extracted.get("cta_buttons", []) if label.strip()}
    actions = {match.group().casefold() for label in cta for match in CTA.finditer(label)}
    cta_score = min(20, (4 if cta else 0) + 8 * len(actions))

    trust = {label.casefold() for label in extracted.get("trust_signals", []) if label.strip()}
    leads = {label.casefold() for label in extracted.get("lead_magnets", []) if label.strip()}
    breakdown = dict(zip(CRITERIA, (uvp, prices, cta_score, min(20, 6 * len(trust)), min(20, 6 * len(leads)))))
    return sum(breakdown.values()), breakdown
