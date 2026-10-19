"""Embeddings des profils et des AO (Sentence Transformers multilingue, exécuté en local) et recherche sémantique."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from functools import lru_cache
from typing import TYPE_CHECKING, Any, Callable

from app import db
from app.config import EMBEDDING_DIM, EMBEDDING_MODEL, SEMANTIC_MATCH_COUNT
from app.search import dedupe_terms, experience_years, find_term, format_years

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer

ProgressCallback = Callable[[int, int], None]


@dataclass
class SemanticMatch:
    candidat_id: str
    similarity: float


@lru_cache(maxsize=1)
def get_model() -> SentenceTransformer:
    # Import tardif : charger torch ralentirait le démarrage de toute l'application
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(EMBEDDING_MODEL)
    if model.get_embedding_dimension() != EMBEDDING_DIM:
        raise RuntimeError(f"{EMBEDDING_MODEL} ne produit pas des vecteurs de dimension {EMBEDDING_DIM}")
    return model


def profile_text(candidat: Mapping[str, Any]) -> str:
    """Texte condensé du profil, du plus au moins discriminant (le modèle tronque au-delà de 128 tokens)."""
    parts = []
    if poste := candidat.get("poste"):
        parts.append(f"Poste : {poste}")
    if (years := experience_years(candidat)) is not None:
        parts.append(f"Expérience : {format_years(years)}")
    if technologies := candidat.get("technologies"):
        parts.append(f"Technologies : {', '.join(technologies)}")
    if competences := candidat.get("competences"):
        parts.append(f"Compétences : {', '.join(competences)}")
    return ". ".join(parts)


def appel_offre_text(ao: Mapping[str, Any]) -> str:
    """Profil recherché par l'AO, au format des profils candidats pour que leurs embeddings soient comparables."""
    required = ao.get("competences_obligatoires") or []
    # Les technologies exigées d'abord (« Java 17 » pour « Java ») : le modèle tronque au-delà de 128 tokens
    technologies = sorted(
        ao.get("technologies") or [],
        key=lambda technology: not any(find_term(skill, [technology]) for skill in required),
    )
    # Une compétence déjà citée parmi les technologies ne consomme pas de tokens une seconde fois
    competences = [
        skill
        for skill in dedupe_terms([*required, *(ao.get("competences_souhaitees") or [])])
        if find_term(skill, technologies) is None
    ]
    return profile_text(
        {
            "poste": ao.get("poste") or ao.get("titre"),
            "experience_annees": ao.get("experience_min_annees"),
            "technologies": technologies,
            "competences": competences,
        }
    )


def embed_texts(texts: list[str]) -> list[list[float]]:
    # Vecteurs normalisés : la distance cosinus de pgvector suffit au classement
    vectors = get_model().encode(texts, normalize_embeddings=True, convert_to_numpy=True)
    return vectors.tolist()


def embed_profile(candidat: Mapping[str, Any]) -> list[float] | None:
    """Embedding du profil, ou None si le profil est vide."""
    text = profile_text(candidat)
    return embed_texts([text])[0] if text else None


def embed_appel_offre(ao: Mapping[str, Any]) -> list[float] | None:
    """Embedding du profil recherché par l'AO, ou None si l'AO est vide."""
    text = appel_offre_text(ao)
    return embed_texts([text])[0] if text else None


def backfill_embeddings(on_progress: ProgressCallback | None = None) -> tuple[int, list[str]]:
    """Calcule l'embedding des CV analysés qui n'en ont pas. Retourne (nombre calculé, erreurs)."""
    candidats = db.list_candidats_sans_embedding()
    done, errors = 0, []
    for index, candidat in enumerate(candidats, start=1):
        if on_progress:
            on_progress(index, len(candidats))
        try:
            embedding = embed_profile(candidat)
            if embedding is None:
                errors.append(f"{candidat.get('chemin_fichier')} : profil vide, rien à indexer")
                continue
            db.update_candidat(candidat["id"], {"embedding": embedding})
            done += 1
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{candidat.get('chemin_fichier')} : {exc}")
    return done, errors


def semantic_search(
    query: str,
    *,
    experience_min: float | None = None,
    experience_max: float | None = None,
    include_unknown_experience: bool = False,
    limit: int = SEMANTIC_MATCH_COUNT,
) -> list[SemanticMatch]:
    """Candidats analysés les plus proches de la requête, du plus au moins pertinent."""
    query_embedding = embed_texts([query.strip()])[0]
    rows = db.match_candidats(
        query_embedding,
        limit=limit,
        experience_min=experience_min,
        experience_max=experience_max,
        include_unknown_experience=include_unknown_experience,
    )
    return [SemanticMatch(str(row["id"]), float(row["similarity"])) for row in rows]
