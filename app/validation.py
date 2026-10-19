"""Contrôles communs des réponses de l'IA (CV et appels d'offres)."""

from __future__ import annotations

import re
from typing import Any, Callable

from app.config import MAX_EXPERIENCE_YEARS

# Ajoute une incertitude : (nom du champ, explication)
Flag = Callable[[str, str], None]

MAX_LIST_ITEMS = 60
MAX_LIST_ITEM_LENGTH = 200
_EMPTY_VALUES = {"", "null", "none", "n/a", "na", "inconnu", "non renseigne", "non renseigné", "-"}

NULLABLE_STRING = {"type": ["string", "null"]}
NULLABLE_NUMBER = {"type": ["number", "null"]}
NULLABLE_STRING_LIST = {"type": ["array", "null"], "items": {"type": "string"}}
STRING_LIST = {"type": "array", "items": {"type": "string"}}


def validate_text(raw: Any, name: str, max_length: int, flag: Flag) -> str | None:
    """Texte nettoyé, ou None si absent, mal typé ou anormalement long."""
    if raw is not None and not isinstance(raw, str):
        flag(name, f"type invalide ignoré ({type(raw).__name__})")
        return None
    value = as_string(raw)
    if value and len(value) > max_length:
        flag(name, f"valeur aberrante ignorée ({value[:40]}…)")
        return None
    return value


def validate_list(raw: Any, name: str, flag: Flag) -> list[str] | None:
    """Liste de textes sans doublons, ou None si absente ou mal typée."""
    if raw is not None and not isinstance(raw, (list, str)):
        flag(name, f"type invalide ignoré ({type(raw).__name__})")
        return None
    return as_string_list(raw)


def validate_years(raw: Any, name: str, flag: Flag) -> float | None:
    """Nombre d'années plausible (0 à MAX_EXPERIENCE_YEARS), arrondi au dixième."""
    if raw is None:
        return None
    if isinstance(raw, bool):
        flag(name, "type invalide ignoré (bool)")
        return None
    if isinstance(raw, str):
        match = re.search(r"\d+(?:[.,]\d+)?", raw)
        if not match:
            flag(name, f"valeur non numérique ignorée ({raw[:40]})")
            return None
        raw = float(match.group().replace(",", "."))
    if not isinstance(raw, (int, float)):
        flag(name, f"type invalide ignoré ({type(raw).__name__})")
        return None
    if not 0 <= raw <= MAX_EXPERIENCE_YEARS:
        flag(name, f"valeur aberrante ignorée ({raw})")
        return None
    return round(float(raw), 1)


def as_string(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    value = " ".join(value.split())
    return None if value.casefold() in _EMPTY_VALUES else value


def as_string_list(value: Any) -> list[str] | None:
    if value is None:
        return None
    items = re.split(r"[,;\n]", value) if isinstance(value, str) else value
    if not isinstance(items, list):
        return None

    unique: dict[str, str] = {}
    for item in items:
        text = as_string(item)
        if text and len(text) <= MAX_LIST_ITEM_LENGTH:
            unique.setdefault(text.casefold(), text)
    return list(unique.values())[:MAX_LIST_ITEMS] or None


def is_flagged(name: str, incertitudes: list[str]) -> bool:
    """Vrai si une incertitude « <name> : … » existe déjà."""
    return any(entry.split(":", 1)[0].strip().casefold() == name for entry in incertitudes)
