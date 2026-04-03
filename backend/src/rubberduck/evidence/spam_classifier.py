"""Heuristic spam classifier for email messages.

Uses a scoring system based on email headers, content patterns, and
sender characteristics to classify emails as spam/newsletter/notification
vs. personal/business communications.

No external APIs or ML models required — runs entirely offline.
"""

import re
from typing import Any

# ── Spam indicator patterns ──────────────────────────────────

# Domains that almost always send marketing/notifications
_BULK_SENDER_DOMAINS = {
    # Email service providers (ESPs)
    "mailchimp.com", "sendgrid.net", "constantcontact.com", "mailgun.org",
    "amazonses.com", "mandrillapp.com", "sparkpostmail.com", "sailthru.com",
    "mcsv.net", "list-manage.com", "hubspot.com", "marketo.com",
    "pardot.com", "eloqua.com", "exacttarget.com", "em.rsys.net",
    "cmail19.com", "cmail20.com", "createsend.com", "ccsend.com",
    "move2inbox.com", "m2i.in", "mailonspot.com", "buzz-india.com",
    # Social media
    "facebookmail.com", "linkedin.com", "twitter.com", "x.com",
    "instagram.com", "tiktok.com", "pinterest.com", "reddit.com",
    "quora.com", "medium.com", "tumblr.com",
    # E-commerce / marketing
    "amazon.com", "amazon.in", "amazon.co.uk", "ebay.com",
    "marketing.angel.co", "angel.co", "care.lenovo.com",
    # News/content/job platforms
    "christianpost.com", "faithit.com", "substack.com",
    "timesjobs.com", "shine.com", "jobsalert.shine.com",
    "riseconf.com", "websummit.com",
    # Misc marketing / commercial
    "myopportunity.email", "parkcreekdata.com",
    "e.davidyurman.com", "nc.faithit.com",
    "godaddy.com", "e.godaddy.com", "lenovo.com", "care.lenovo.com",
    "newsstand.com", "newstand.com", "safehavenleads.com",
    "beneficialmarketing.co.uk", "flipkart.com", "myntra.com",
    "paytm.com", "zomato.com", "swiggy.in", "makemytrip.com",
    "goibibo.com", "bookmyshow.com", "naukri.com", "monster.com",
    "indeed.com", "glassdoor.com", "groupon.com", "udemy.com",
    "coursera.org", "skillshare.com",
    # ESP relay domains
    "mkt.com", "mktomail.com", "pages.email",
    # Job sites / recruitment
    "monsterindia.com", "monster.co.in",
    # Telecom / utilities
    "vodafone.com", "ebill.vodafone.com", "airtel.in",
    # Auth / notifications
    "accounts.google.com", "notifications.skype.com", "skype.com",
    # Marketing agencies
    "deepbluem.com", "finessedirect.com",
    "indiafilings.email", "referralkey.com",
    # Conference / events
    "ubs-transformance.com",
    # Petitions / campaigns
    "change.org",
    # Freelance / gig platforms
    "guru.com", "fiverr.com", "upwork.com", "freelancer.com",
    # Financial services (often phishing/marketing)
    "westernunion.com", "em.westernunion.com",
    # Career / recruitment
    "ettcareermove.com",
    # Indian classifieds / job alerts
    "quikr.com", "olx.in", "sulekha.com",
    "techgig.com", "careerbuilder.com", "alerts.careerbuilder.com",
    # Dating / social apps
    "tubely.com", "tinder.com", "bumble.com",
    # Medical coding / marketing companies
    "ccmedicalsolutions.com", "learnmedicalcoding.com",
    "hbma.org",
    # Maven / newsletter platforms
    "maven.co",
    # E-commerce (Indian)
    "reply.ebay.in", "ebay.in", "flipkartletters.com",
    "snapdeal.com", "shopclues.com", "jabong.com",
}

# Tracking/ESP URL fragments that appear in email bodies
_TRACKING_URL_PATTERNS = [
    re.compile(r"move2inbox", re.I),
    re.compile(r"list-manage\.com", re.I),
    re.compile(r"track\.\d+mail\d+\.", re.I),  # track.724mail200.xxx
    re.compile(r"mailchimp\.com/track", re.I),
    re.compile(r"sendgrid\.net/wf/click", re.I),
    re.compile(r"mandrillapp\.com/track", re.I),
    re.compile(r"ccsend\.com", re.I),
    re.compile(r"click\?u=.*&id=.*&e=", re.I),  # Mailchimp click tracking
    re.compile(r"/track/click\?", re.I),
    re.compile(r"/track-url/", re.I),
    re.compile(r"email\.mg\.", re.I),  # Mailgun
    re.compile(r"rs6\.net", re.I),  # Constant Contact
]

# Header patterns indicating bulk/automated mail
_BULK_HEADERS_PATTERNS = [
    re.compile(r"list-unsubscribe", re.I),
    re.compile(r"x-mailer.*mailchimp|sendgrid|hubspot|marketo|salesforce", re.I),
    re.compile(r"precedence:\s*(bulk|list|junk)", re.I),
    re.compile(r"x-campaign|x-mailgun|x-ses|x-sg-|x-mandrill", re.I),
]

# Subject patterns typical of newsletters/notifications
_NOTIFICATION_SUBJECT_PATTERNS = [
    re.compile(r"(your|new)\s+(order|receipt|invoice|statement|bill)", re.I),
    re.compile(r"(password|account)\s+(reset|verification|confirm)", re.I),
    re.compile(r"(shipping|delivery)\s+(confirmation|update|notification)", re.I),
    re.compile(r"\bunsubscribe\b", re.I),
    re.compile(r"(weekly|daily|monthly)\s+(digest|newsletter|update|summary|recap)", re.I),
    re.compile(r"(new|latest)\s+(features?|update|release|version)", re.I),
    re.compile(r"(don.?t miss|limited time|act now|last chance|expires)", re.I),
    re.compile(r"(off|discount|deal|sale|promo|coupon|save)\s+\d+%?", re.I),
    re.compile(r"(verify|confirm)\s+your\s+(email|account|identity)", re.I),
    re.compile(r"(invitation to join|discover opportunities)", re.I),
    re.compile(r"(now shipping|avail.*offer|exclusive offer)", re.I),
    re.compile(r"(shortlisted|screening call|updated resume|updated profile)", re.I),
    re.compile(r"(hiring|we can help|looking for.*talent|recruitment|job opening)", re.I),
    re.compile(r"(final notice|account.*suspended|verify.*immediately|urgent.*action)", re.I),
    re.compile(r"(take action|sign.*petition|your voice|support.*cause)", re.I),
    re.compile(r"(inbound.*project|direct.*client|call center|bpo|outsourc)", re.I),
    re.compile(r"(free trial|get started|sign up|register now|join now)", re.I),
    re.compile(r"(ramadan|diwali|christmas|holiday|festival).*\b(sale|discount|offer|special)\b", re.I),
]

# Body content patterns typical of spam/marketing
_SPAM_BODY_PATTERNS = [
    re.compile(r"(click here|tap here|view in browser)", re.I),
    re.compile(r"(unsubscribe|opt[- ]?out|manage preferences)", re.I),
    re.compile(r"(this email was sent|you received this|you are receiving)", re.I),
    re.compile(r"(privacy policy|terms of service|terms and conditions)", re.I),
    re.compile(r"\u00a9\s*\d{4}", re.I),  # Copyright symbol + year
    re.compile(r"(view this email|trouble viewing|images aren't displaying)", re.I),
    re.compile(r"(manage your preferences|email preferences|notification settings)", re.I),
    re.compile(r"open in next tab", re.I),
    re.compile(r"(email not displaying|view as web page|view online)", re.I),
    re.compile(r"(powered by|sent via)\s+(mailchimp|sendgrid|hubspot|constant\s*contact)", re.I),
    re.compile(r"(accept invitation|update now|apply now|shop now|buy now|order now)", re.I),
]

# Sender address prefixes that indicate automated/bulk mail
_AUTOMATED_SENDER_PREFIXES = re.compile(
    r"^(info|newsletter|newsletters|marketing|notifications?|updates?|promo|deals|"
    r"sales|team|hello|hi|alerts?|digest|news|store-news|talent|connections|"
    r"invitations|messages-noreply|groups-noreply|notification\+|mailer|campaign|"
    r"support|donotreply|do-not-reply|announce|admin|system|automated|batch|"
    r"bulletin|offer|confirm|verify|service|billing|receipt|order|delivery|"
    r"shipping|tracking|signup|welcome|onboarding|feedback|survey|rewards|"
    r"membership|subscription|account|security|helpdesk|care|customercare|"
    r"connector|jobmessenger|jobs|careers|talent-team|recruitment|"
    r"campaigns|news|offers|deals|ebill|bill|invoice|"
    r"no-reply|noreply|do-not-reply|donotreply)@",
    re.I,
)

# Social media keywords in sender
_SOCIAL_KEYWORDS = [
    "linkedin", "facebook", "twitter", "instagram", "tiktok",
    "pinterest", "quora", "reddit", "youtube", "snapchat", "whatsapp",
]


def classify_email(
    *,
    email_from: str = "",
    email_to: str = "",
    subject: str = "",
    body: str = "",
    headers_raw: str = "",
    has_attachments: bool = False,
    recipient_count: int = 1,
) -> dict[str, Any]:
    """Classify an email and return spam score + classification.

    Returns a dict with:
        is_spam: bool
        spam_score: float (0.0-1.0)
        spam_reasons: list[str]
        classification: str (personal, business, newsletter, notification, spam, unknown)
    """
    score = 0.0
    reasons: list[str] = []

    from_lower = email_from.lower()
    subject_lower = subject.lower()
    body_preview = body[:3000].lower() if body else ""

    # ── Sender analysis ──────────────────────────
    # Check if sender domain is a known bulk mailer
    from_domain = ""
    from_address = ""
    if "@" in from_lower:
        from_address = from_lower.split("<")[-1].strip(">").strip() if "<" in from_lower else from_lower
        from_domain = from_address.split("@")[-1].strip(">").strip()

    for bulk_domain in _BULK_SENDER_DOMAINS:
        if bulk_domain in from_domain:
            score += 0.4
            reasons.append(f"bulk sender domain: {bulk_domain}")
            break

    # "noreply" or "no-reply" sender
    if "noreply" in from_lower or "no-reply" in from_lower or "donotreply" in from_lower:
        score += 0.3
        reasons.append("noreply sender")

    # ALL CAPS sender display name (e.g. "ROHIT VERMA <...@gmail.com>")
    # Legitimate senders almost never use ALL CAPS display names
    if "<" in email_from:
        display_name = email_from.split("<")[0].strip().strip('"').strip("'")
        name_words = display_name.split()
        if len(name_words) >= 2 and display_name == display_name.upper() and any(c.isalpha() for c in display_name):
            score += 0.25
            reasons.append("ALL CAPS sender display name")

    # Automated sender prefix
    if _AUTOMATED_SENDER_PREFIXES.match(from_address):
        score += 0.2
        reasons.append("automated sender prefix")

    # Brand impersonation in display name (phishing signal)
    _IMPERSONATED_BRANDS = ["western union", "american express", "paypal", "apple", "microsoft",
                            "amazon", "netflix", "bank of", "wells fargo", "chase", "citibank",
                            "hsbc", "barclays", "fedex", "ups", "dhl", "irs", "hmrc"]
    if "<" in email_from:
        display_lower = email_from.split("<")[0].strip().strip('"').strip("'").lower()
        actual_addr = email_from.split("<")[-1].strip(">").lower()
        for brand in _IMPERSONATED_BRANDS:
            if brand in display_lower and brand.split()[0] not in actual_addr:
                score += 0.4
                reasons.append(f"brand impersonation: {brand}")
                break

    # Social media notification senders
    if any(kw in from_lower for kw in _SOCIAL_KEYWORDS):
        score += 0.15
        reasons.append("social media notification sender")

    # ── Header analysis ──────────────────────────
    for pattern in _BULK_HEADERS_PATTERNS:
        if pattern.search(headers_raw):
            score += 0.25
            reasons.append(f"bulk header: {pattern.pattern[:40]}")
            break  # One header match is enough

    # ── Subject analysis ─────────────────────────
    for pattern in _NOTIFICATION_SUBJECT_PATTERNS:
        if pattern.search(subject):
            score += 0.15
            reasons.append("notification subject pattern")
            break

    # ALL CAPS subject (3+ words) — strong spam signal
    words = subject.split()
    if len(words) >= 3 and subject == subject.upper() and any(c.isalpha() for c in subject):
        score += 0.25
        reasons.append("ALL CAPS subject")

    # Exclamation marks or excessive punctuation in subject (marketing)
    if subject.count("!") >= 2 or subject.count("?") >= 3:
        score += 0.1
        reasons.append("excessive punctuation in subject")

    # Very long subject (marketing emails tend to have long subjects)
    if len(subject) > 120:
        score += 0.1
        reasons.append("very long subject line")

    # Sender domain has marketing/ESP-like subdomain patterns
    # e.g. e.godaddy.com, care.lenovo.com, nc.faithit.com
    if from_domain and re.match(r"^(e|m|mail|email|marketing|promo|news|campaign|go|click|track|send|bulk|info|offers?|notify|alerts?|updates?)\.", from_domain):
        score += 0.25
        reasons.append("marketing subdomain prefix")

    # Sender domain uses unusual TLDs common in marketing
    if from_domain and any(from_domain.endswith(tld) for tld in [".email", ".marketing", ".promo", ".deals", ".buzz", ".click", ".link", ".info"]):
        score += 0.2
        reasons.append("marketing TLD in sender domain")

    # Sender domain contains marketing-related words
    if from_domain and any(kw in from_domain for kw in ["marketing", "leads", "promo", "campaign", "mailer", "newsletter", "broadcast", "bulk", "blast"]):
        score += 0.35
        reasons.append("marketing keyword in sender domain")

    # Encoded =?utf-8? subjects usually indicate bulk mailers
    # (personal email clients decode these before sending)
    if "=?utf" in subject or "=?iso" in subject.lower():
        score += 0.2
        reasons.append("MIME-encoded subject (bulk mailer)")

    # ── Body analysis ────────────────────────────
    body_matches = 0
    for pattern in _SPAM_BODY_PATTERNS:
        if pattern.search(body_preview):
            body_matches += 1

    if body_matches >= 4:
        score += 0.4
        reasons.append(f"many spam body patterns ({body_matches})")
    elif body_matches >= 2:
        score += 0.25
        reasons.append(f"multiple spam body patterns ({body_matches})")
    elif body_matches >= 1:
        score += 0.15
        reasons.append(f"spam body pattern ({body_matches})")

    # Check for ESP tracking URLs in body
    tracking_matches = 0
    for pattern in _TRACKING_URL_PATTERNS:
        if pattern.search(body_preview):
            tracking_matches += 1

    if tracking_matches >= 1:
        score += 0.3
        reasons.append(f"ESP tracking URL in body ({tracking_matches} match)")

    # Body is mostly just URLs / tracking links (no real content)
    if body_preview and len(body_preview) > 50:
        non_url_text = re.sub(r"https?://\S+", "", body_preview).strip()
        url_ratio = 1.0 - (len(non_url_text) / len(body_preview))
        if url_ratio > 0.6:
            score += 0.2
            reasons.append("body is mostly tracking URLs")

    # Body is also ALL CAPS (strong spam signal combined with ALL CAPS subject)
    if body_preview and len(body_preview) > 30:
        alpha_chars = [c for c in body_preview if c.isalpha()]
        if alpha_chars:
            upper_ratio = sum(1 for c in alpha_chars if c.isupper()) / len(alpha_chars)
            if upper_ratio > 0.7:
                score += 0.2
                reasons.append("ALL CAPS body content")

    # Very short or empty body (notification pattern)
    if body and len(body.strip()) < 50:
        score += 0.05

    # ── Combined signals (multiple weak signals = strong) ─────
    # ALL CAPS sender name + any body spam pattern = likely bulk
    has_caps_sender = "ALL CAPS sender display name" in reasons
    has_caps_subject = "ALL CAPS subject" in reasons
    if has_caps_sender and body_matches >= 1:
        score += 0.15
        reasons.append("combined: ALL CAPS sender + spam body")
    if has_caps_subject and has_caps_sender:
        score += 0.1
        reasons.append("combined: ALL CAPS sender + subject")

    # ── Positive signals (reduce spam score) ─────
    # Reply/forward = almost certainly personal
    if re.search(r"^(re|fwd|fw):\s", subject, re.I):
        score -= 0.4
        reasons.append("reply/forward (likely personal)")

    # Short recipient list is more personal
    if recipient_count == 1:
        score -= 0.05

    # Personalized greeting addressing the recipient by name
    # (many spam does this too, so small signal)
    if re.search(r"^(hi|hey|hello|dear)\s+[a-z]+[,!]?\s", body_preview):
        score -= 0.05

    # Clamp score
    score = max(0.0, min(1.0, score))

    # Determine classification
    is_spam = score >= 0.5
    if score >= 0.7:
        classification = "spam"
    elif score >= 0.5:
        classification = "newsletter"
    elif score >= 0.3:
        classification = "notification"
    elif "sent" in from_lower or from_lower.startswith("me "):
        classification = "sent"
    else:
        classification = "personal"

    return {
        "is_spam": is_spam,
        "spam_score": round(score, 3),
        "spam_reasons": reasons,
        "classification": classification,
    }
