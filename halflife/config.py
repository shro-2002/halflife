"""Runtime settings, read once from the environment (.env)."""

import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


@dataclass(frozen=True)
class Settings:
    bifrost_url: str
    admin_user: str
    admin_password: str
    virtual_key: str
    model: str
    fallback_models: tuple[str, ...]
    model_cutoff: date
    relay_name: str
    cache_dir: Path
    db_path: Path


def _virtual_key() -> str:
    if os.environ.get("HALFLIFE_VK"):
        return os.environ["HALFLIFE_VK"]
    vk_file = ROOT / ".cache" / "vk.txt"
    return vk_file.read_text().strip() if vk_file.exists() else ""


def load_settings() -> Settings:
    port = os.environ.get("BIFROST_PORT", "8088")
    fallbacks = os.environ.get("HALFLIFE_FALLBACK_MODELS", "anthropic/claude-haiku-4-5")
    return Settings(
        bifrost_url=os.environ.get("BIFROST_URL", f"http://localhost:{port}").rstrip("/"),
        admin_user=os.environ.get("BIFROST_ADMIN_USERNAME", ""),
        admin_password=os.environ.get("BIFROST_ADMIN_PASSWORD", ""),
        virtual_key=_virtual_key(),
        model=os.environ.get("HALFLIFE_MODEL", "anthropic/claude-haiku-5-5"),
        fallback_models=tuple(m for m in fallbacks.split(",") if m),
        # Reliable knowledge cutoff of Claude Haiku 5.5 per Anthropic's models overview: Jun 2026.
        model_cutoff=date.fromisoformat(os.environ.get("HALFLIFE_MODEL_CUTOFF", "2026-06-30")),
        relay_name=os.environ.get("HALFLIFE_TAVILY_RELAY", "tavily"),
        cache_dir=Path(os.environ.get("HALFLIFE_CACHE_DIR", ROOT / ".cache" / "tavily")),
        db_path=Path(os.environ.get("HALFLIFE_DB", ROOT / "data" / "ledger.sqlite")),
    )
