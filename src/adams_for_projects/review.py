"""Versioned, deterministic reading priority from ADAMS titles only.

This is editorial triage, not an NRC finding or a safety-severity assessment.
One contextual rule supplies the rank; themes never add points.  Keep this
module dependency-free so the site can reassess retained metadata identically.
"""
from __future__ import annotations

import re
from typing import Any

REVIEW_VERSION = "2.0.0"


def _has(text: str, pattern: str) -> bool:
    return re.search(pattern, text, re.IGNORECASE) is not None


def _themes(t: str) -> list[str]:
    patterns = (
        ("Waste and storage", r"\b(?:spent fuel|dry casks?|canisters?|isfsi|radioactive waste|waste disposal|waste storage|low[- ]level waste)\b"),
        ("Decommissioning and finance", r"\b(?:decommissioning|trust funds?|financial qualifications?|financial assurance|funding|financing)\b"),
        ("Exemptions and licensing", r"\b(?:exemptions?|relief requests?|licen[cs](?:e|es|ing)|technical specifications?|uprat(?:e|es)|restart|construction permits?|risk-informed|performance-based|lar)\b"),
        ("Equipment and operations", r"\b(?:licensee event reports?|ler|part\s*21|defects?|inoperab\w*|fail(?:ure|ures|ed)|safety function|diesel generators?|offsite power)\b"),
        ("Environmental review", r"\b(?:environmental assessments?|environmental impact|fonsi|finding of no significant impact|nepa)\b"),
        ("Emergency planning and security", r"\b(?:emergency planning|epz|security|safeguards|fingerprinting)\b"),
        ("Enforcement and oversight", r"\b(?:enforcement|confirmatory (?:orders?|action letters?)|demand for information|violations?|allegations?|investigations?|inspection reports?)\b"),
        ("Policy and rulemaking", r"\b(?:rulemaking|proposed rules?|final rules?|executive orders?|presidential orders?|regulatory reform)\b"),
        ("Public participation", r"\b(?:public (?:meetings?|comments?)|comments?\s*\(|hearings?|intervenors?|intervene|contentions?|petitions?)\b"),
    )
    result = [label for label, pattern in patterns if _has(t, pattern)]
    # A public/non-proprietary copy is not evidence that material was withheld.
    access_text = re.sub(r"\b(?:non[- ]?proprietary|not proprietary|no (?:information |material )?withheld|without redactions?)\b", "", t)
    if _has(access_text, r"\b(?:proprietary|withheld|redact(?:ed|ions?)|foia|public access|protective order|access to (?:safeguards|sensitive))\b"):
        result.append("Information access")
    return result


def classify_title(title: str) -> dict[str, Any]:
    """Return the stable review contract; priority describes reading order only.

    HIGH >= 70, MEDIUM >= 40, BACKGROUND < 40. Ranks are rule precedence,
    not an additive risk score. Reasons state what the title identifies.
    """
    t = re.sub(r"\s+", " ", (title or "").replace("\u2013", "-").replace("\u2014", "-")).strip().lower()
    themes = _themes(t)

    def result(rank: int, kind: str, reason: str) -> dict[str, Any]:
        return {
            "version": REVIEW_VERSION,
            "basis": "title",
            "priority": "HIGH" if rank >= 70 else "MEDIUM" if rank >= 40 else "BACKGROUND",
            "document_type": kind,
            "reasons": [reason],
            "themes": themes,
            "rank_score": rank,
        }

    if not t:
        return result(0, "Unclassified record", "No title is available for classification.")

    # Identify the document's role before interpreting words quoted in its subject.
    # These overrides deliberately stay narrow: an 'administrative order' or a
    # 'notice of violation' is not discarded merely for administrative wording.
    if _has(t, r"\b(?:typographical|typographic|clerical|editorial) (?:errors?|corrections?|changes?)\b|\bcorrect(?:ion|ing) (?:of |to )?(?:a |the )?typographical\b|\berrata\b"):
        return result(15, "Editorial correction", "Title identifies an editorial or typographical correction.")
    if _has(t, r"\b(?:correction pages|wordperfect conversion)\b"):
        return result(15, "Editorial correction", "Title identifies correction pages or a document-conversion error.")
    if _has(t, r"\b(?:correction to issuance|corrected (?:copy|pages))\b"):
        return result(40, "Document correction", "Title identifies a correction to an earlier document; its scope requires review.")
    if _has(t, r"\b(?:collection renewal|collection of information|supporting statement for|nrc form (?:396|398))\b"):
        return result(25, "Information-collection material", "Title identifies a form, information collection, or its supporting statement.")
    if _has(t, r"\b(?:task order|purchase order|delivery order|invoice submissions?|contract modification)\b"):
        return result(10, "Procurement record", "Title identifies procurement or invoicing material.")
    if _has(t, r"\breduced order model(?:ing|s)?\b"):
        return result(25, "Research reference", "Title identifies modeling research; 'order' is not an enforcement action.")
    if _has(t, r"^(?:ip\s*\d{4,5}\b|inspection (?:procedure|manual)\b)|\b(?:inspection manual chapter|training (?:manual|course|slides|on|material|presentation|module)|opinions and decisions .{0,80}selected orders)\b"):
        return result(20, "Procedure or reference", "Title identifies a procedure, training item, or reference collection.")
    if _has(t, r"\b(?:request for guidance|guidance (?:document|on)|reporting requirements)\b") and not _has(t, r"\b(?:proposed rule|final rule|petition for rulemaking|revision to|revised guidance)\b"):
        return result(30, "Guidance or interpretation", "Title identifies guidance or a request for interpretation.")
    if _has(t, r"\b(?:certificate of service|distribution list|form 890|acknowledg(?:e)?ment of receipt|form 532)\b"):
        return result(10, "Administrative filing", "Title identifies service, distribution, or receipt paperwork.")
    if _has(t, r"\b(?:information request|inspection plan|inspection preparation)\b") and _has(t, r"\b(?:ip\s*\d{4,5}|inspection)\b"):
        return result(45, "Inspection preparation", "Title identifies preparation or an information request for an inspection.")

    # Procedural scheduling is background; a merits decision that also sets a
    # schedule is assessed later as an adjudicatory decision.
    if _has(t, r"\b(?:page limit|motion to file a reply brief|brief in support|petition to intervene|joint motion|unopposed motion|intervenors?[’\']? motion)\b"):
        if _has(t, r"\b(?:page limit|motion to file a reply brief)\b"):
            return result(20, "Scheduling or procedure", "Title identifies a procedural filing limit or briefing permission.")
        return result(50, "Public participation or filing", "Title identifies a participant filing concerning a proceeding.")
    merits = _has(t, r"\b(?:denying|granting|dismiss(?:ing|al)|ruling on|terminating|revoking|suspending)\b.{0,100}\b(?:contentions?|hearing requests?|request for hearing|summary disposition|proceeding|licen[cs]es?)\b")
    if not merits and _has(t, r"\b(?:scheduling|rescheduling|briefing schedule|establishing (?:a )?(?:briefing )?schedule|establishing deadline|extension of time|extend (?:the )?(?:deadline|discovery period)|page limit|initial prehearing order|case opening order|status conference|scheduling and management order|establishment of atomic safety and licensing board)\b"):
        return result(20, "Scheduling or procedure", "Title identifies scheduling or procedural administration.")
    if _has(t, r"\b(?:agenda|meeting notice|notice of (?:a )?(?:public )?meeting|to hold (?:first |a )?public meeting)\b"):
        return result(30, "Meeting notice or agenda", "Title identifies a meeting notice or agenda.")
    if _has(t, r"\b(?:meeting summary|summary of (?:.{0,45} )?(?:a |public )?meeting|public meeting (?:slides|presentation|summary)|slides for .{0,60}meeting|transcript)\b"):
        return result(45, "Meeting material", "Title identifies meeting discussion or presentation material.")
    if _has(t, r"\bpublic meeting\b"):
        return result(35, "Meeting material", "Title identifies a public meeting; its subject does not establish a new decision.")
    if not merits and _has(t, r"\bcomments?\s*\(|\b(?:public comments?|comments? (?:on|regarding)|petition to intervene|request for hearing|motion (?:to|for)|brief in support|joint response|intervenor.{0,25}(?:brief|response))\b"):
        return result(50, "Public participation or filing", "Title identifies a comment, petition, motion, or participant filing.")

    # Do not interpret a negated condition as a positive report of that condition.
    conditions = re.sub(r"\b(?:no|without) (?:reported |identified |evidence of |a )?(?:loss of (?:a )?safety function|defects?|failures?|violations?)\b", "", t)
    if _has(t, r"\b(?:licensee event report|ler)\b"):
        return result(96, "Licensee event report", "Title identifies a licensee event report.")
    if _has(conditions, r"\b(?:loss of (?:a )?safety function|inability to fulfill .{0,35}safety function|condition prohibited by .{0,30}technical specifications?|loss of offsite power|reactor trip|unplanned (?:shutdown|scram)|unplanned (?:radioactive )?release)\b"):
        return result(94, "Reported operating condition", "Title describes an operating condition or loss of a safety function.")
    if _has(t, r"\bpart\s*21\b") and _has(conditions, r"\b(?:report|notification|update|evaluation|defects?|failure)\b") and not _has(t, r"\b(?:program implementation|quality assurance program)\b"):
        return result(93, "Part 21 report or update", "Title identifies a Part 21 report, notification, or evaluation.")
    if _has(conditions, r"\b(?:inoperable|failed|failure|defect)\b") and _has(t, r"\b(?:report|notification|event|safety|generator|relay|breaker|valve|pump|actuator|switch|battery|cable)\b"):
        return result(90, "Reported equipment condition", "Title describes an equipment condition for review.")
    if _has(t, r"\b(?:trust fund|financial assurance|decommissioning fund|funding)\b") and _has(t, r"\b(?:shortfall|deficien(?:cy|cies)|underfund(?:ed|ing)|insufficient)\b") and not _has(t, r"\b(?:no|without) (?:a )?(?:funding )?(?:shortfall|deficien(?:cy|cies))\b"):
        return result(88, "Funding concern", "Title identifies a funding shortfall or deficiency.")

    # Enforcement follow-up and requested relaxation are distinguished from the
    # underlying order. A procurement/policy/adjudicatory order never enters on
    # the bare word 'order'.
    if _has(t, r"\benforcement guidance memorandum\b"):
        return result(75, "Enforcement policy guidance", "Title identifies guidance affecting enforcement policy.")
    enforcement = _has(t, r"\b(?:confirmatory order|confirmatory action letter|demand for information|enforcement order|administrative order.{0,25}enforcement|notice of violation|civil penalty|order (?:prohibiting|revoking|suspending)|enforcement (?:action|discretion)|investigation report)\b")
    if enforcement:
        if _has(t, r"\b(?:relaxation|extension request|request for .{0,35}(?:relaxation|extension)|request.*enforcement discretion)\b"):
            return result(68, "Enforcement-related request", "Title identifies a request affecting enforcement conditions.")
        if _has(t, r"\b(?:annual (?:summary|status)|status update|response to|acceptance of|confirmation of compliance|commitments|audit report|effectiveness review|corrective actions complete|closure notification|inspection readiness|listing of materials|storage update)\b"):
            return result(64, "Enforcement follow-up", "Title identifies a response or follow-up to an enforcement matter.")
        return result(92, "Enforcement action or finding", "Title identifies an enforcement action, violation notice, or investigation report.")
    if _has(t, r"\b(?:allegation|allegations)\b"):
        return result(66, "Allegation-related record", "Title identifies an allegation-related matter; the title does not establish its findings.")

    if merits:
        return result(74, "Adjudicatory decision", "Title identifies a ruling on a contention, hearing request, or proceeding.")
    if _has(t, r"\b(?:protective order|withholding|redactions?|foia|public access|access to (?:safeguards|sensitive))\b"):
        return result(58, "Information-access matter", "Title identifies information-access procedures or a withholding/redaction matter.")
    if _has(t, r"\b(?:final rule|direct final rule|adopt(?:ed|ion) .{0,40}rule)\b") and not _has(t, r"\b(?:draft|proposed)\b.{0,15}\bfinal rule\b"):
        return result(80, "Rule or policy decision", "Title identifies a final rule or adopted regulatory change.")
    if _has(t, r"\b(?:rulemaking|proposed rule|executive order|presidential order|regulatory reform)\b"):
        return result(62, "Policy or rulemaking", "Title identifies policy implementation or rulemaking activity.")

    subject = _has(t, r"\b(?:exemption|relief|licen[cs](?:e|es|ing)|amendment|construction permit|decommissioning|trust fund|spent fuel|isfsi|uprate|restart|emergency planning|epz|security|safeguards|risk-informed|performance-based|lar)\b")
    request = _has(t, r"\b(?:request(?:ing|s)?|application|proposed|draft|acceptance review|review of|audit plan|estimated completion)\b")
    decision = _has(t, r"\b(?:issuance|issued|grant(?:ed|ing)?|den(?:ied|ying)|approv(?:ed|ing|al)|final order|order revoking|order terminating|order imposing (?:additional )?requirements|amendment no[.]?\s*\d+)\b")
    # A request containing the words 'order approving' is still an application.
    if _has(t, r"\b10 cfr 50[.]59 report\b"):
        return result(52, "Regulatory follow-up", "Title identifies a regulatory report listing program or technical changes.")
    if subject and _has(t, r"\b(?:response to|closure notification|confirmation of compliance)\b"):
        return result(52, "Regulatory follow-up", "Title identifies a follow-up or periodic report concerning a regulatory matter.")
    if subject and decision and not request:
        return result(76, "Licensing or regulatory decision", "Title identifies an issued decision or approval affecting licensing or regulatory conditions.")
    if _has(t, r"\bdraft\b") and _has(t, r"\b(?:environmental assessment|environmental impact|finding of no significant impact|fonsi|ea)\b"):
        return result(60, "Draft environmental review", "Title identifies a draft environmental assessment or finding for review.")
    if _has(t, r"\b(?:final environmental (?:assessment|impact statement)|finding of no significant impact|fonsi)\b"):
        return result(72, "Environmental review finding", "Title identifies an environmental review finding or final assessment.")
    if _has(t, r"\b(?:environmental assessment|environmental impact|nepa)\b"):
        return result(60, "Environmental review", "Title identifies environmental review material.")
    if _has(t, r"\b(?:trust fund|decommissioning (?:fund|funding))\b") and _has(t, r"\b(?:annual report|status|summary|biennial|funding assurance report)\b"):
        return result(48, "Periodic funding report", "Title identifies a periodic funding report; it does not by itself establish a shortfall.")
    if _has(t, r"\b(?:inspection|audit) (?:report|of)|\b(?:inspection|audit)\b.{0,50}\bprogram implementation\b"):
        return result(58, "Inspection or audit", "Title identifies an inspection or audit record; findings require reading the document.")
    if _has(t, r"\b(?:request for additional information|response to .{0,30}additional information|\brai\b)\b"):
        return result(54, "Review correspondence", "Title identifies a request for additional information or a response.")
    if subject and request:
        return result(62, "Application or regulatory request", "Title identifies an application, proposed change, or regulatory request.")
    if _has(t, r"\b(?:exemptions?|relief requests?|technical specifications?|financial qualifications?|financial assurance|decommissioning|trust fund|spent fuel|dry casks?|canisters?|isfsi|uprate|restart|emergency planning|risk-informed|performance-based|lar)\b"):
        return result(50, "Regulatory or technical record", "Title identifies licensing, waste, financial, or operational material for review.")
    if _has(t, r"\b(?:memorandum and order|order of the secretary|commission .{0,20}order|court order)\b"):
        return result(42, "Adjudicatory record", "Title identifies an order but does not specify a substantive outcome.")
    if _has(t, r"\b(?:public meeting|meeting)\b"):
        return result(35, "Meeting material", "Title identifies meeting-related material.")
    if _has(t, r"\b(?:proprietary|non[- ]?proprietary|redacted)\b"):
        return result(25, "Supporting material", "Copy markings alone do not establish a substantive development.")
    return result(20, "Unclassified record", "The title does not identify a clear substantive action; document review is needed.")
