import re

# Best-effort keyword heuristics for common wg-gesucht / rental scam patterns.
# This flags for human review — it never blocks or auto-replies. False
# negatives are expected; treat every reply asking for money or documents
# with normal caution regardless of whether it gets flagged here.
RED_FLAGS = [
    ("payment before viewing",
     r"(kaution|deposit).{0,30}(vorab|im voraus|vor der besichtigung|before.{0,15}(viewing|seeing)|in advance|upfront)"),
    ("wire transfer / non-reversible payment",
     r"western union|moneygram|paypal.{0,20}(friends|family)|freunde.{0,15}familie"),
    ("landlord claims to be abroad / can't show in person",
     r"(im ausland|currently abroad|overseas|missionar)|kann.{0,20}nicht.{0,20}(besichtig|zeigen)|cannot.{0,20}show.{0,20}(in person|myself)"),
    ("keys sent by courier/mail",
     r"schl(ü|u)ssel.{0,20}(post|kurier)|keys?.{0,20}(courier|mail|shipped)"),
    ("urgency pressure to pay immediately",
     r"sofort (ü|u)berweisen|dringend.{0,15}(überweis|zahlen)|pay.{0,15}(immediately|right away|now)"),
    ("asks to move off-platform immediately with payment talk",
     r"(whatsapp|hangouts).{0,60}(überweis|deposit|kaution|payment)"),
]

COMPILED = [(name, re.compile(pattern, re.IGNORECASE)) for name, pattern in RED_FLAGS]


def find_scam_flags(text: str) -> list[str]:
    hits = []
    for name, pattern in COMPILED:
        if pattern.search(text):
            hits.append(name)
    return hits
