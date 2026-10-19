"""Recherche multicritère des candidats : compétences/technologies, poste, expérience."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

# Garde « + », « # » et les points internes pour distinguer C, C++, C#, Node.js…
_TOKEN = re.compile(r"[a-z0-9+#]+(?:\.[a-z0-9+#]+)*")
_TERM_SEPARATORS = re.compile(r"[,;+\n]")


class Mode(str, Enum):
    ALL = "ET"
    ANY = "OU"


@dataclass(frozen=True)
class SearchCriteria:
    terms: tuple[str, ...] = ()
    mode: Mode = Mode.ALL
    poste: str = ""
    experience_min: float | None = None
    experience_max: float | None = None
    include_unknown_experience: bool = False

    @property
    def is_empty(self) -> bool:
        return not (
            self.terms
            or self.poste.strip()
            or self.experience_min is not None
            or self.experience_max is not None
        )


@dataclass
class SearchResult:
    candidat: Mapping[str, Any]
    found: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    to_check: list[str] = field(default_factory=list)
    matched_terms: int = 0


def tokens(text: str) -> list[str]:
    """Mots normalisés : minuscules, sans accents."""
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    return _TOKEN.findall(ascii_text)


def parse_terms(text: str) -> tuple[str, ...]:
    """« Java + Spring, Docker » -> ("Java", "Spring", "Docker"), sans doublons."""
    return dedupe_terms(_TERM_SEPARATORS.split(text))


def dedupe_terms(terms: Iterable[str]) -> tuple[str, ...]:
    unique: dict[tuple[str, ...], str] = {}
    for term in terms:
        key = tuple(tokens(term))
        if key:
            unique.setdefault(key, term.strip())
    return tuple(unique.values())


def find_term(term: str, items: Iterable[str]) -> str | None:
    """Premier élément contenant le terme comme suite de mots entiers.

    « Spring » trouve « Spring Boot », mais « Java » ne trouve pas « JavaScript ».
    """
    needle = tokens(term)
    if not needle:
        return None
    size = len(needle)
    for item in items:
        haystack = tokens(item)
        if any(haystack[i : i + size] == needle for i in range(len(haystack) - size + 1)):
            return item
    return None


def search_candidats(
    candidats: Iterable[Mapping[str, Any]], criteria: SearchCriteria
) -> list[SearchResult]:
    """Candidats satisfaisant les critères, les plus pertinents d'abord."""
    results = [r for c in candidats if (r := _evaluate(c, criteria)) is not None]
    results.sort(key=lambda r: (-r.matched_terms, -(experience_years(r.candidat) or 0)))
    return results


def _evaluate(candidat: Mapping[str, Any], criteria: SearchCriteria) -> SearchResult | None:
    result = SearchResult(candidat)

    items = [*(candidat.get("competences") or []), *(candidat.get("technologies") or [])]
    for term in criteria.terms:
        item = find_term(term, items)
        if item is None:
            result.missing.append(term)
        else:
            same = tokens(item) == tokens(term)
            result.found.append(term if same else f"{term} ({item})")
            result.matched_terms += 1

    if criteria.terms:
        if criteria.mode is Mode.ALL and result.missing:
            return None
        if criteria.mode is Mode.ANY and not result.matched_terms:
            return None

    poste_query = tokens(criteria.poste)
    if poste_query:
        poste = " ".join(tokens(candidat.get("poste") or ""))
        if not all(word in poste for word in poste_query):
            return None
        result.found.append(f"Poste : {criteria.poste.strip()}")

    if criteria.experience_min is not None or criteria.experience_max is not None:
        years = experience_years(candidat)
        if years is None:
            if not criteria.include_unknown_experience:
                return None
            result.to_check.append("Expérience inconnue")
        elif _within(years, criteria.experience_min, criteria.experience_max):
            result.found.append(f"Expérience : {format_years(years)}")
        else:
            return None

    return result


def experience_years(candidat: Mapping[str, Any]) -> float | None:
    value = candidat.get("experience_annees")
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def format_years(years: float) -> str:
    """1 -> « 1 an », 1.5 -> « 1,5 an », 3 -> « 3 ans »."""
    unit = "ans" if years >= 2 else "an"
    return f"{years:g} {unit}".replace(".", ",")


def _within(years: float, minimum: float | None, maximum: float | None) -> bool:
    return (minimum is None or years >= minimum) and (maximum is None or years <= maximum)
