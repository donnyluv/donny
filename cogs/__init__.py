"""Вспомогательные утилиты для пакета с когами."""

from __future__ import annotations

from importlib import util as importlib_util
from pathlib import Path
import sys
import types

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_DATABASE_PATH = _PROJECT_ROOT / "database.py"


def _ensure_project_root_on_path() -> None:
    root_str = str(_PROJECT_ROOT)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)


def get_database_module() -> types.ModuleType:
    """Возвращает модуль базы данных, загружая его при необходимости."""

    existing_module = sys.modules.get("database")
    if isinstance(existing_module, types.ModuleType):
        return existing_module

    _ensure_project_root_on_path()

    spec = importlib_util.spec_from_file_location("database", _DATABASE_PATH)
    if spec is None or spec.loader is None:
        raise ImportError(
            "Не удалось загрузить модуль базы данных по пути " f"{_DATABASE_PATH}"
        )

    module = importlib_util.module_from_spec(spec)
    loader = spec.loader
    loader.exec_module(module)

    sys.modules["database"] = module
    return module


__all__ = ["get_database_module"]