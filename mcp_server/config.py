"""Configuration for RenderDoc MCP Server"""

import json
import os
from pathlib import Path


# Default config file search paths
_CONFIG_SEARCH_PATHS = [
    Path.cwd() / "renderdoc_mcp_config.json",
    Path.home() / ".renderdoc_mcp" / "config.json",
]

# Package root (parent of mcp_server/)
_PKG_ROOT = Path(__file__).parent.parent


def _find_config_file() -> Path | None:
    """Search for config file in standard locations."""
    # Environment variable override
    env_path = os.environ.get("RENDERDOC_MCP_CONFIG")
    if env_path:
        p = Path(env_path)
        if p.is_file():
            return p

    for path in _CONFIG_SEARCH_PATHS:
        if path.is_file():
            return path

    return None


def _load_json_config(path: Path) -> dict:
    """Load JSON config file."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


class Settings:
    """Server settings with JSON config file and environment variable support."""

    def __init__(self):
        # Load JSON config if available
        config_path = _find_config_file()
        self._file_config = _load_json_config(config_path) if config_path else {}
        self._config_path = config_path

        # --- RenderDoc Bridge ---
        self.renderdoc_host = self._get("renderdoc_host", "RENDERDOC_MCP_HOST", "127.0.0.1")
        self.renderdoc_port = int(self._get("renderdoc_port", "RENDERDOC_MCP_PORT", "19876"))

        # --- Compiler Paths ---
        compiler_dir = _PKG_ROOT / "mobile_offline_compilers"
        self.malioc_path = self._get(
            "malioc_path", "MALIOC_PATH",
            str(compiler_dir / "malioc.exe"),
        )
        self.aoc_path = self._get(
            "aoc_path", "AOC_PATH",
            str(compiler_dir / "aoc.exe"),
        )

        # --- Default GPU Targets ---
        self.mali_default_core = self._get("mali_default_core", "MALI_DEFAULT_CORE", "Mali-G78")
        self.adreno_default_arch = self._get("adreno_default_arch", "ADRENO_DEFAULT_ARCH", "a650")

    def _get(self, key: str, env_key: str, default: str) -> str:
        """Get a setting value. Priority: env var > JSON config > default."""
        env_val = os.environ.get(env_key)
        if env_val is not None:
            return env_val
        file_val = self._file_config.get(key)
        if file_val is not None:
            return str(file_val)
        return default


settings = Settings()
