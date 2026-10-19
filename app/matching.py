"""Matching AO ↔ candidats : score pondéré, transparent et recalculable à la main."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any

from app.embeddings import embed_appel_offre, embed_texts, profile_text
from app.search import experience_years, find_term, format_years


class Criterion(str, Enum):
    REQUIRED = "Compétences obligatoires"
    DESIRED = "Compétences souhaitées"
    EXPERIENCE = "Expérience"
    SEMANTIC = "Similarité sémantique"


# Points maximum par critère (total 100)
WEIGHTS: dict[Criterion, int] = {
    Criterion.REQUIRED: 45,
    Criterion.DESIRED: 15,
    Criterion.EXPERIENCE: 15,
    Criterion.SEMANTIC: 25,
}


class SkillStatus(str, Enum):
    ACQUIRED = "Acquise"
    UNPROVEN = "Non démontrée"
    MISSING = "Manquante"


# Part des points d'une compétence selon l'endroit où elle est trouvée
SKILL_CREDIT: dict[SkillStatus, float] = {
    SkillStatus.ACQUIRED: 1.0,
    SkillStatus.UNPROVEN: 0.5,
    SkillStatus.MISSING: 0.0,
}
STRONG_SIMILARITY = 0.7
_FICHE_FIELDS = ("competences", "technologies", "certifications", "langues")


@dataclass(frozen=True)
class SkillMatch:
    skill: str
    status: SkillStatus
    # Élément de la fiche qui contient la compétence (ex. « Spring Boot 3 » pour « Spring Boot »)
    evidence: str | None = None


@dataclass(frozen=True)
class CriterionScore:
    criterion: Criterion
    points: float
    formula: str
    detail: str
    applicable: bool = True

    @property
    def weight(self) -> int:
        return WEIGHTS[self.criterion]


@dataclass(frozen=True)
class MatchResult:
    candidat: Mapping[str, Any]
    criteria: tuple[CriterionScore, ...]
    required: tuple[SkillMatch, ...]
    desired: tuple[SkillMatch, ...]
    strengths: tuple[str, ...]

    @property
    def score(self) -> float:
        """Somme des points arrondis affichés : le total se vérifie à la main."""
        return round(sum(c.points for c in self.criteria), 1)

    @property
    def gaps(self) -> tuple[SkillMatch, ...]:
        """Compétences obligatoires manquantes ou non démontrées."""
        return tuple(m for m in self.required if m.status is not SkillStatus.ACQUIRED)

    def criterion(self, criterion: Criterion) -> CriterionScore:
        return next(c for c in self.criteria if c.criterion is criterion)


def rank_candidats(
    ao: Mapping[str, Any],
    candidats: list[Mapping[str, Any]],
    ao_embedding: list[float] | None = None,
) -> list[MatchResult]:
    """Score de chaque candidat pour l'AO, du plus au moins compatible."""
    if ao_embedding is None:
        ao_embedding = embed_appel_offre(ao)

    embeddings = {c["id"]: c.get("embedding") for c in candidats}
    # Embedding pas encore calculé : calcul à la volée (non enregistré) pour ne pénaliser personne
    missing = [c for c in candidats if not embeddings[c["id"]] and profile_text(c)]
    if missing:
        for candidat, vector in zip(missing, embed_texts([profile_text(c) for c in missing])):
            embeddings[candidat["id"]] = vector

    results = [
        score_candidat(ao, c, _cosine(ao_embedding, embeddings[c["id"]])) for c in candidats
    ]
    results.sort(key=lambda r: (-r.score, -r.criterion(Criterion.REQUIRED).points))
    return results


def score_candidat(ao: Mapping[str, Any], candidat: Mapping[str, Any], similarity: float | None) -> MatchResult:
    required = evaluate_skills(ao.get("competences_obligatoires"), candidat)
    desired = evaluate_skills(ao.get("competences_souhaitees"), candidat)
    criteria = (
        _skills_score(Criterion.REQUIRED, required),
        _skills_score(Criterion.DESIRED, desired),
        _experience_score(_as_float(ao.get("experience_min_annees")), experience_years(candidat)),
        _semantic_score(similarity),
    )
    return MatchResult(candidat, criteria, required, desired, _strengths(required, desired, criteria, similarity))


def evaluate_skills(skills: Iterable[str] | None, candidat: Mapping[str, Any]) -> tuple[SkillMatch, ...]:
    """Acquise si la fiche la contient, non démontrée si seul le texte du CV la cite, sinon manquante."""
    items = [item for name in _FICHE_FIELDS for item in candidat.get(name) or []]
    texte = candidat.get("texte_brut") or ""
    matches = []
    for skill in skills or []:
        evidence = find_term(skill, items)
        if evidence is not None:
            matches.append(SkillMatch(skill, SkillStatus.ACQUIRED, evidence))
        elif find_term(skill, [texte]) is not None:
            matches.append(SkillMatch(skill, SkillStatus.UNPROVEN))
        else:
            matches.append(SkillMatch(skill, SkillStatus.MISSING))
    return tuple(matches)


def criterion_gaps(a: MatchResult, b: MatchResult) -> list[tuple[Criterion, float]]:
    """Écart de points (a − b) par critère, du plus grand au plus petit en valeur absolue."""
    gaps = [(c, round(a.criterion(c).points - b.criterion(c).points, 1)) for c in Criterion]
    return sorted(gaps, key=lambda gap: -abs(gap[1]))


def format_number(value: float) -> str:
    """32.5 -> « 32,5 », 45.0 -> « 45 », 0.87 -> « 0,87 »."""
    return f"{round(value, 2):g}".replace(".", ",")


def _skills_score(criterion: Criterion, matches: tuple[SkillMatch, ...]) -> CriterionScore:
    weight = WEIGHTS[criterion]
    if not matches:
        return CriterionScore(
            criterion,
            float(weight),
            f"{weight} (non précisé par l'AO)",
            f"L'AO ne précise pas de {criterion.value.lower()} : points attribués à tous",
            applicable=False,
        )

    counts = {status: sum(m.status is status for m in matches) for status in SkillStatus}
    acquired, unproven, missing = (counts[s] for s in SkillStatus)
    credit = sum(SKILL_CREDIT[m.status] for m in matches)
    total = len(matches)
    numerator = f"({acquired} + {unproven} × 0,5)" if unproven else str(acquired)
    return CriterionScore(
        criterion,
        round(credit / total * weight, 1),
        f"{numerator} / {total} × {weight}",
        f"{_count(acquired, 'acquise')}, {_count(unproven, 'non démontrée')}, "
        f"{_count(missing, 'manquante')} sur {total}",
    )


def _experience_score(expected: float | None, years: float | None) -> CriterionScore:
    weight = WEIGHTS[Criterion.EXPERIENCE]
    if expected is None:
        return CriterionScore(
            Criterion.EXPERIENCE,
            float(weight),
            f"{weight} (non précisé par l'AO)",
            "L'AO ne chiffre pas l'expérience attendue : points attribués à tous",
            applicable=False,
        )
    if years is None:
        return CriterionScore(
            Criterion.EXPERIENCE, 0.0, "0 (expérience inconnue)", "Expérience du candidat non renseignée"
        )

    detail = f"Candidat : {format_years(years)} · AO : {format_years(expected)} minimum"
    if expected == 0 or years >= expected:
        return CriterionScore(Criterion.EXPERIENCE, float(weight), f"1 × {weight} (minimum atteint)", detail)
    return CriterionScore(
        Criterion.EXPERIENCE,
        round(years / expected * weight, 1),
        f"{format_number(years)} / {format_number(expected)} × {weight}",
        detail,
    )


def _semantic_score(similarity: float | None) -> CriterionScore:
    weight = WEIGHTS[Criterion.SEMANTIC]
    if similarity is None:
        return CriterionScore(
            Criterion.SEMANTIC, 0.0, "0 (embedding indisponible)", "Profil ou AO trop vide pour être comparé"
        )
    # Arrondie avant le calcul pour que la formule affichée donne exactement les points
    similarity = round(max(similarity, 0.0), 2)
    return CriterionScore(
        Criterion.SEMANTIC,
        round(similarity * weight, 1),
        f"{format_number(similarity)} × {weight}",
        "Proximité de sens entre le profil recherché et le profil du candidat (0 à 1)",
    )


def _strengths(
    required: tuple[SkillMatch, ...],
    desired: tuple[SkillMatch, ...],
    criteria: tuple[CriterionScore, ...],
    similarity: float | None,
) -> tuple[str, ...]:
    strengths = []
    acquired = [m for m in required if m.status is SkillStatus.ACQUIRED]
    if required and len(acquired) == len(required):
        strengths.append(f"Toutes les compétences obligatoires sont acquises ({len(required)}/{len(required)})")
    elif required and len(acquired) >= 0.75 * len(required):
        strengths.append(f"{len(acquired)}/{len(required)} compétences obligatoires acquises")

    assets = [m.skill for m in desired if m.status is SkillStatus.ACQUIRED]
    if assets:
        strengths.append(f"Atouts souhaités par l'AO : {', '.join(assets)}")

    experience = next(c for c in criteria if c.criterion is Criterion.EXPERIENCE)
    if experience.applicable and experience.points == experience.weight:
        strengths.append(f"Expérience suffisante ({experience.detail})")

    if similarity is not None and similarity >= STRONG_SIMILARITY:
        strengths.append(f"Profil très proche de l'AO (similarité {format_number(round(similarity, 2))})")
    return tuple(strengths)


def _cosine(a: list[float] | None, b: list[float] | None) -> float | None:
    # Embeddings normalisés à l'enregistrement : le produit scalaire est la similarité cosinus
    if not a or not b:
        return None
    return sum(x * y for x, y in zip(a, b))


def _as_float(value: Any) -> float | None:
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def _count(n: int, word: str) -> str:
    return f"{n} {word}{'s' if n > 1 else ''}"
