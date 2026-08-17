"""
Registry mapping source names (as used in config/profile.yaml `sources.enabled`)
to adapter instances. Adding a new source = add one file in sources/ + one line here.
"""
from __future__ import annotations

from src.scraper.sources.arbeitnow import ArbeitnowSource
from src.scraper.sources.base import SourceAdapter
from src.scraper.sources.generic_playwright import GenericPlaywrightSource
from src.scraper.sources.remoteok import RemoteOKSource

_REGISTRY: dict[str, type] = {
    "remoteok": RemoteOKSource,
    "arbeitnow": ArbeitnowSource,
    "generic_playwright": GenericPlaywrightSource,
}


def build_sources(enabled_names: list[str]) -> list[SourceAdapter]:
    sources = []
    for name in enabled_names:
        cls = _REGISTRY.get(name)
        if cls is None:
            raise ValueError(
                f"Unknown source '{name}' in profile.yaml sources.enabled. "
                f"Known sources: {list(_REGISTRY.keys())}"
            )
        sources.append(cls())
    return sources
