"""Agenti della pipeline (uno per responsabilità)."""

from .research import ResearchAgent
from .screening import ScreeningAgent
from .verification import VerificationAgent
from .extraction import ExtractionAgent
from .quality import QualityAgent
from .synthesis import SynthesisAgent
from .athlete import AthleteContextAgent

__all__ = [
    "ResearchAgent",
    "ScreeningAgent",
    "VerificationAgent",
    "ExtractionAgent",
    "QualityAgent",
    "SynthesisAgent",
    "AthleteContextAgent",
]
