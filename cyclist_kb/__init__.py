"""cyclist_kb — Knowledge base scientifica auto-mantenuta sull'allenamento ciclistico.

MVP locale: pipeline multi-agente che recupera, deduplica, valuta, verifica ed
estrae letteratura scientifica, sintetizzandola in una wiki Markdown versionata.
Non addestra alcun modello: usa API di LLM esistenti (o euristiche offline) e
banche dati bibliografiche pubbliche.
"""

__version__ = "0.1.0"
