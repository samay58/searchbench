from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict

from dotenv import load_dotenv

try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:  # pragma: no cover - fallback for 3.10
    import tomli as tomllib


DEFAULT_TIMEOUTS: Dict[str, int] = {
    "default": 30,
    "exa": 30,
    "parallel": 30,
    "brave": 20,
    "linkup": 25,
    "tavily": 20,
}

DEFAULT_CONFIG_PATH = Path("config.toml")


@dataclass(frozen=True)
class Settings:
    timeouts: Dict[str, int]
    results_dir: Path


def load_settings(config_path: Path | None = None) -> Settings:
    load_dotenv()

    path = config_path or DEFAULT_CONFIG_PATH
    data: dict = {}
    if path.exists():
        data = tomllib.loads(path.read_text())

    timeouts = DEFAULT_TIMEOUTS.copy()
    configured = data.get("timeouts", {})
    for key, value in configured.items():
        try:
            timeouts[str(key)] = int(value)
        except (TypeError, ValueError):
            continue

    results_dir = Path(data.get("results_dir", "results"))
    return Settings(timeouts=timeouts, results_dir=results_dir)


def timeout_for(provider: str, settings: Settings) -> int:
    return settings.timeouts.get(provider, settings.timeouts["default"])
