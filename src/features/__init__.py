"""Реестр блоков признаков. У каждого блока одинаковый интерфейс (CLAUDE.md, раздел 6)."""
import importlib

BLOCK_MODULES = {
    "base": "src.features.base",
    "a": "src.features.profile",
    "b": "src.features.velocity",
    "c": "src.features.context",
}


def get_block(name: str):
    return importlib.import_module(BLOCK_MODULES[name])
