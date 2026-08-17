"""
Every job source (API-based or scraped) implements this same tiny interface.
Adding a new source later = one new file here + registering it in registry.py.
Nothing else in the pipeline needs to know or care how a given source works
internally (see docs/ARCHITECTURE.md §3).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class RawPosting:
    """The one shape every adapter must produce, regardless of how it got the data."""

    source: str
    url: str
    title: str | None = None
    company: str | None = None
    raw_text: str | None = None
    raw_payload: dict[str, Any] = field(default_factory=dict)


class SourceAdapter(Protocol):
    """Structural interface — any object with a matching `fetch` is a valid source."""

    name: str

    async def fetch(self) -> list[RawPosting]:
        """Return every posting this source currently has. Must never raise on a
        single bad item — log + skip it, return whatever succeeded."""
        ...
