"""Locate shared data in a source checkout or a normal wheel installation."""
from pathlib import Path
import sysconfig


def data_directory() -> Path:
    checkout = Path(__file__).resolve().parents[2] / "data"
    installed = Path(sysconfig.get_path("data")) / "share" / "scriptmate"
    for candidate in (checkout, installed):
        if (candidate / "keyword_mapping.json").is_file():
            return candidate
    raise FileNotFoundError("ScriptMate data is missing. Reinstall the ScriptMate package.")
