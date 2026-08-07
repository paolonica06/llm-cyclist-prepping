"""Vocabolario di dominio: sinonimi, marcatori di popolazione e disegni di studio.

Usato dalle euristiche offline (generazione query, screening, qualità) così che
la pipeline resti sensata anche senza LLM. Con LLM disponibile questi insiemi
fungono comunque da segnali di supporto e audit.
"""

from __future__ import annotations

from typing import Dict, List

# Espansione sinonimica per la generazione delle query.
SYNONYMS: Dict[str, List[str]] = {
    "interval training": [
        "high-intensity interval training", "HIIT", "sprint interval training", "SIT",
        "interval exercise", "high intensity intervals",
    ],
    "vo2max": [
        "VO2max", "VO2 max", "maximal oxygen uptake", "maximal oxygen consumption",
        "aerobic capacity", "peak oxygen uptake", "VO2peak",
    ],
    "cyclist": ["cyclists", "cycling", "road cyclists", "competitive cyclists", "trained cyclists"],
    "trained": ["trained", "well-trained", "highly trained", "endurance-trained", "elite", "competitive"],
    "endurance": ["endurance", "aerobic", "stamina"],
    "performance": ["performance", "time trial", "power output", "peak power"],
    "threshold": ["lactate threshold", "anaerobic threshold", "functional threshold power", "FTP"],
}

# Marcatori per la classificazione della popolazione (screening).
CYCLING_MARKERS = [
    "cyclist", "cyclists", "cycling", "road bike", "mountain bike", "mtb",
    "cycle ergometer", "cycling ergometer", "bicycle", "track cycling", "time trial",
    "peloton", "watt", "ftp",
]
ENDURANCE_OTHER_MARKERS = [
    "runner", "running", "rowing", "rower", "swimmer", "swimming", "triathlete",
    "triathlon", "cross-country skiing", "skier", "marathon", "middle-distance",
    "speed skating", "kayak",
]
UNTRAINED_MARKERS = [
    "untrained", "sedentary", "recreationally active", "physically inactive",
    "healthy untrained", "novice", "non-athletes", "inactive adults", "obese",
    "overweight", "clinical population", "patients",
]
TRAINED_MARKERS = [
    "trained", "well-trained", "highly trained", "elite", "competitive",
    "professional", "endurance-trained", "national level", "world class",
]
# Popolazioni cliniche/non atletiche palesemente estranee al dominio (pazienti di
# patologie non legate allo sport, neonati, gravidanza). Escludono SOLO in assenza
# di segnale ciclistico/allenato — uno studio su "cyclists with type 1 diabetes"
# resta ammissibile perché CYCLING_MARKERS/TRAINED_MARKERS lo compensano.
CLINICAL_NONATHLETE_MARKERS = [
    "type 2 diabetes", "diabetes mellitus", "diabetic patients", "chronic kidney disease",
    "dialysis", "cancer patients", "oncology", "chemotherapy", "copd",
    "chronic obstructive pulmonary", "heart failure patients", "postoperative",
    "post-surgical", "neonate", "neonatal", "newborn", "infant", "infants",
    "pediatric patients", "pregnant", "pregnancy",
]

# Marcatori del disegno dello studio (qualità).
STUDY_DESIGN_MARKERS: Dict[str, List[str]] = {
    "meta-analysis": ["meta-analysis", "meta analysis", "systematic review and meta"],
    "systematic review": ["systematic review", "scoping review"],
    "review": ["review", "narrative review"],
    "randomized controlled trial": ["randomized controlled trial", "randomised controlled trial",
                                     "rct", "randomly assigned", "randomized", "randomised"],
    "crossover": ["crossover", "cross-over", "counterbalanced"],
    "cohort": ["cohort", "longitudinal", "prospective"],
    "case-control": ["case-control", "case control"],
    "cross-sectional": ["cross-sectional", "cross sectional", "observational"],
    "case study": ["case study", "case report", "single subject", "n-of-1"],
}

# Gerarchia indicativa dei disegni (livello di evidenza). Usata per scegliere il
# disegno più forte quando più marcatori compaiono nello stesso testo.
DESIGN_RANK = {
    "meta-analysis": 5, "systematic review": 5,
    "randomized controlled trial": 4, "crossover": 4,
    "cohort": 3, "case-control": 3, "cross-sectional": 2,
    "review": 2, "case study": 1, "unknown": 1,
}


def best_design(low_text: str):
    """Ritorna il disegno con rank più alto fra i marcatori presenti, o None."""
    matched = [d for d, markers in STUDY_DESIGN_MARKERS.items() if any(m in low_text for m in markers)]
    if not matched:
        return None
    return max(matched, key=lambda d: DESIGN_RANK.get(d, 1))


# Contesto di esercizio/fisiologia: serve a scartare falsi positivi in cui parole
# come "cycling" o "performance" compaiono fuori dal dominio (es. batterie, economia).
EXERCISE_CONTEXT_MARKERS = [
    "vo2", "oxygen uptake", "aerobic", "anaerobic", "endurance", "training", "exercise",
    "athlete", "ergometer", "muscle", "hiit", "interval training", "sprint interval",
    "cardiorespiratory", "fitness", "heart rate", "lactate", "physiolog", "workload",
    "watt", "cycling performance", "time trial", "vo2max", "vo2 max", "oxygen consumption",
]

# Frasi che segnalano randomizzazione e controllo (dimensioni di qualità).
RANDOMIZATION_MARKERS = ["random", "randomi"]
CONTROL_MARKERS = ["control group", "placebo", "comparator", "versus", "compared with", "control condition"]
