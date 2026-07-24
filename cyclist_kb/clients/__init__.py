"""Client asincroni per le banche dati bibliografiche.

Ognuno espone `async search(query, limit, research_id) -> List[PaperRecord]` e
normalizza i risultati nello schema comune, taggando `source_dbs` e conservando
il payload grezzo in `raw[<fonte>]`. Tutti degradano con grazia: un errore di
rete restituisce una lista vuota, mai un'eccezione che blocca la pipeline.
"""

from .pubmed import PubMedClient
from .openalex import OpenAlexClient
from .semantic_scholar import SemanticScholarClient
from .crossref import CrossrefClient

__all__ = [
    "PubMedClient",
    "OpenAlexClient",
    "SemanticScholarClient",
    "CrossrefClient",
    "ALL_CLIENTS",
]

ALL_CLIENTS = [PubMedClient, OpenAlexClient, SemanticScholarClient, CrossrefClient]
