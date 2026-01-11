from __future__ import annotations

from typing import Dict, Type

from searchbench.providers.base import Provider, SearchResult

_REGISTRY: Dict[str, Type[Provider]] = {}


def register(provider_cls: Type[Provider]) -> Type[Provider]:
    name = getattr(provider_cls, "name", None)
    if not name:
        raise ValueError("Provider must define a non-empty name")
    _REGISTRY[name] = provider_cls
    return provider_cls


def get_provider(name: str) -> Type[Provider]:
    try:
        return _REGISTRY[name]
    except KeyError as exc:
        raise KeyError(f"Unknown provider: {name}") from exc


def create_provider(name: str, **kwargs) -> Provider:
    provider_cls = get_provider(name)
    return provider_cls(**kwargs)


def list_providers() -> list[str]:
    return sorted(_REGISTRY.keys())


__all__ = ["Provider", "SearchResult", "register", "get_provider", "create_provider", "list_providers"]

# Provider registrations
from searchbench.providers.exa import ExaProvider  # noqa: F401
from searchbench.providers.parallel import ParallelProvider  # noqa: F401
from searchbench.providers.tavily import TavilyProvider  # noqa: F401
from searchbench.providers.brave import BraveProvider  # noqa: F401
from searchbench.providers.linkup import LinkupProvider  # noqa: F401
