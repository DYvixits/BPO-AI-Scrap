from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SearchHit:
    url: str
    title: str
    snippet: str


class SearchProvider(ABC):
    """Provider abstraction (ARCHITECTURE.md §7) — callers depend on this
    interface only, never on a concrete provider, so swapping DuckDuckGo for
    a paid API (Bing, Serper, Tavily, Google CSE) is a one-class change."""

    @abstractmethod
    async def search(self, query: str, *, max_results: int) -> list[SearchHit]:
        raise NotImplementedError
