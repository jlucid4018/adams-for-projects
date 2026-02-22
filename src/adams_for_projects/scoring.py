from __future__ import annotations

from typing import List, Tuple

NOISE_KEYWORDS = {
    "fitness for duty","ffd","drug","alcohol","random test","single positive test",
    "certificate of service","notice of","administrative","distribution list","agenda",
    "transcript","form 890",
}

POSITIVE_KEYWORDS = {
    "confirmatory action letter": 12,
    "demand for information": 12,
    "order": 10,
    "enforcement": 9,
    "allegation": 9,
    "part 21": 9,
    "defect": 8,
    "exemption": 7,
    "relief request": 7,
    "risk-informed": 7,
    "performance-based": 7,
    "emergency planning": 7,
    "epz": 7,
    "fonsi": 6,
    "finding of no significant impact": 6,
    "environmental assessment": 6,
    "spent fuel": 6,
    "dry cask": 6,
    "canister": 6,
    "decommissioning": 6,
    "trust fund": 6,
    "uprate": 6,
    "loss of offsite power": 8,
    "diesel generator": 7,
    "technical specification": 6,
    "proprietary": 5,
    "withheld": 5,
    "redacted": 5,
}

NEGATIVE_KEYWORDS = {
    "fitness for duty": -10,
    "drug": -10,
    "alcohol": -10,
    "single positive test": -10,
    "certificate of service": -8,
    "administrative": -6,
    "distribution list": -6,
    "agenda": -5,
    "transcript": -5,
}

def is_noise(title: str) -> bool:
    t = (title or "").lower()
    return any(k in t for k in NOISE_KEYWORDS)

def score_title(title: str) -> Tuple[int, List[str]]:
    t = (title or "").lower()
    score = 0
    hits: List[str] = []

    for k, w in POSITIVE_KEYWORDS.items():
        if k in t:
            score += w
            hits.append(k)

    for k, w in NEGATIVE_KEYWORDS.items():
        if k in t:
            score += w
            hits.append(f"noise:{k}")

    return score, hits

def doc_bonus(title: str) -> int:
    t = (title or "").lower()
    bonus = 0
    if any(w in t for w in ("attachment","enclosure","cover letter","supplement","appendix","exhibit")):
        bonus -= 2
    if "ltr" in t:
        bonus += 1
    if "request for" in t:
        bonus += 1
    if "memorandum" in t:
        bonus += 1
    return bonus

def infer_angle(title: str, hits: List[str]) -> str:
    h = set(hits)
    t = (title or "").lower()

    if ("risk-informed" in h or "performance-based" in h) and ("emergency planning" in h or "epz" in h):
        return "ANGLE: risk-informed / performance-based emergency planning (EPZ shrink-by-math)"
    if "decommissioning" in h or "trust fund" in h:
        return "ANGLE: decommissioning money carve-outs (trust fund rules + exemptions)"
    if "fonsi" in h or "environmental assessment" in h:
        return "ANGLE: EA/FONSI paperwork shield (environmental findings used as clearance stamp)"
    if "order" in h or "confirmatory action letter" in h or "demand for information" in h:
        return "ANGLE: enforcement theater (orders/CAL/DFI = real pressure points)"
    if "allegation" in h:
        return "ANGLE: allegations pipeline (the stuff that rarely gets daylight)"
    if "part 21" in h or "defect" in h:
        return "ANGLE: Part 21 / defect disclosure (vendor failure meets regulatory language)"
    if "spent fuel" in h or "dry cask" in h or "canister" in h:
        return "ANGLE: waste logistics reality (canisters, aging management, the forever tail)"
    if "uprate" in h:
        return "ANGLE: tiny % gain, huge system risk (uprate economics vs. complexity)"
    if "withheld" in h or "proprietary" in h or "redacted" in h:
        return "ANGLE: redaction theater (public access, private details)"
    if "loss of offsite power" in h or "diesel generator" in h:
        return "ANGLE: external power dependency (the part PR never leads with)"

    if "exemption" in t:
        return "ANGLE: exemption request (rules bent to keep timelines moving)"
    if "meeting" in t:
        return "ANGLE: meeting choreography (process as a product)"
    return "ANGLE: project-grade doc (needs opening)"
