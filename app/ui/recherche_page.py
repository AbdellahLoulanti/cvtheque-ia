"""Page Recherche : onglet multicritère et onglet sémantique (embeddings + pgvector)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd
import streamlit as st

from app import db
from app.config import MAX_EXPERIENCE_YEARS, STATUT_ANALYSE, is_supabase_configured
from app.embeddings import backfill_embeddings, semantic_search
from app.search import (
    Mode,
    SearchCriteria,
    SearchResult,
    dedupe_terms,
    experience_years,
    parse_terms,
    search_candidats,
)
from app.ui.fiche import display_name, render_fiche_by_id

_MODE_LABELS = {Mode.ALL: "Toutes (ET)", Mode.ANY: "Au moins une (OU)"}


@dataclass(frozen=True)
class ExperienceFilter:
    minimum: float | None
    maximum: float | None
    include_unknown: bool


def render() -> None:
    st.header("Recherche")

    if not is_supabase_configured():
        st.error("Supabase n'est pas configuré : renseignez SUPABASE_URL et SUPABASE_KEY dans .env.")
        return

    try:
        candidats = [c for c in db.list_candidats() if c.get("statut") == STATUT_ANALYSE]
    except Exception as exc:  # noqa: BLE001
        st.error(f"Lecture des candidats impossible : {exc}")
        return

    if not candidats:
        st.info("Aucun CV analysé : lancez l'analyse IA depuis la page Import.")
        return

    criteria_tab, semantic_tab = st.tabs(["Critères", "Sémantique"])
    with criteria_tab:
        _render_criteria_tab(candidats)
    with semantic_tab:
        _render_semantic_tab(candidats)


# --- Onglet Critères ---

def _render_criteria_tab(candidats: list[dict[str, Any]]) -> None:
    st.caption("Combinez compétences, technologies, poste et expérience. La casse et les accents sont ignorés.")

    criteria = _render_criteria(candidats)
    if criteria is None:
        return
    if criteria.is_empty:
        st.caption(f"Renseignez au moins un critère pour chercher parmi les {len(candidats)} CV analysés.")
        return

    results = search_candidats(candidats, criteria)
    st.subheader(f"{len(results)} candidat(s) sur {len(candidats)} CV analysés")
    if not results:
        st.info("Aucun candidat ne correspond à ces critères.")
        return

    selected_id = _render_criteria_results(results, criteria)
    _render_selected_fiche(selected_id, key="criteres_fiche")


def _render_criteria(candidats: list[dict[str, Any]]) -> SearchCriteria | None:
    """Affiche les filtres ; retourne None si la saisie est incohérente."""
    vocabulary = sorted(
        dedupe_terms(
            item
            for c in candidats
            for item in (*(c.get("competences") or []), *(c.get("technologies") or []))
        ),
        key=str.casefold,
    )

    terms_column, mode_column = st.columns([3, 1])
    selected = terms_column.multiselect(
        "Compétences et technologies",
        vocabulary,
        accept_new_options=True,
        placeholder="Ex. Java, Spring, Docker…",
        help="Choisissez dans la liste ou tapez un terme puis Entrée. « Spring » trouve aussi « Spring Boot ».",
    )
    mode = mode_column.radio(
        "Le candidat doit avoir", list(Mode), format_func=_MODE_LABELS.get, horizontal=True
    )

    poste_column, min_column, max_column = st.columns([2, 1, 1])
    poste = poste_column.text_input("Intitulé de poste", placeholder="Ex. développeur, DevOps…")
    experience = _render_experience_filter("criteres", min_column, max_column)
    if experience is None:
        return None

    return SearchCriteria(
        # Un terme saisi « Java + Spring » compte pour deux critères
        terms=dedupe_terms(term for entry in selected for term in parse_terms(entry)),
        mode=mode,
        poste=poste,
        experience_min=experience.minimum,
        experience_max=experience.maximum,
        include_unknown_experience=experience.include_unknown,
    )


def _render_criteria_results(results: list[SearchResult], criteria: SearchCriteria) -> str | None:
    """Affiche le tableau des résultats et retourne l'id du candidat sélectionné."""
    table = pd.DataFrame(
        {
            "id": [r.candidat["id"] for r in results],
            "Candidat": [display_name(r.candidat) for r in results],
            "Poste": [r.candidat.get("poste") for r in results],
            "Expérience (ans)": [experience_years(r.candidat) for r in results],
            "Termes": [f"{r.matched_terms}/{len(criteria.terms)}" for r in results],
            "Critères trouvés": [r.found for r in results],
            "Critères manquants": [r.missing for r in results],
            "À vérifier": [r.to_check for r in results],
        }
    )

    columns = ["Candidat", "Poste", "Expérience (ans)"]
    if criteria.terms:
        columns.append("Termes")
    columns.append("Critères trouvés")
    if any(r.missing for r in results):
        columns.append("Critères manquants")
    if any(r.to_check for r in results):
        columns.append("À vérifier")

    return _selectable_table(
        table,
        columns,
        {
            "Termes": st.column_config.TextColumn(help="Compétences / technologies trouvées sur le total demandé"),
            "Critères trouvés": st.column_config.ListColumn(width="large"),
            "Critères manquants": st.column_config.ListColumn(),
            "À vérifier": st.column_config.ListColumn(),
        },
        key=f"recherche_table_{hash(criteria)}",
    )


# --- Onglet Sémantique ---

def _render_semantic_tab(candidats: list[dict[str, Any]]) -> None:
    st.caption(
        "Décrivez le profil recherché avec vos propres mots : les candidats sont classés par proximité de sens, "
        "même si leur CV n'emploie pas les mêmes termes."
    )

    if not _render_backfill():
        return

    query = st.text_input(
        "Profil recherché",
        placeholder="Ex. développeur backend Java expérimenté",
        key="semantique_requete",
    )
    min_column, max_column, _ = st.columns([1, 1, 2])
    experience = _render_experience_filter("semantique", min_column, max_column)
    if experience is None:
        return
    if not query.strip():
        st.caption("Saisissez une description pour lancer la recherche.")
        return

    try:
        with st.spinner("Recherche en cours…"):
            matches = semantic_search(
                query,
                experience_min=experience.minimum,
                experience_max=experience.maximum,
                include_unknown_experience=experience.include_unknown,
            )
    except Exception as exc:  # noqa: BLE001
        st.error(f"Recherche sémantique impossible : {exc}")
        return

    by_id = {c["id"]: c for c in candidats}
    matches = [m for m in matches if m.candidat_id in by_id]
    st.subheader(f"{len(matches)} candidat(s) classé(s) par pertinence")
    if not matches:
        st.info("Aucun candidat ne correspond à ces filtres.")
        return

    table = pd.DataFrame(
        {
            "id": [m.candidat_id for m in matches],
            "Candidat": [display_name(by_id[m.candidat_id]) for m in matches],
            "Poste": [by_id[m.candidat_id].get("poste") for m in matches],
            "Expérience (ans)": [experience_years(by_id[m.candidat_id]) for m in matches],
            "Pertinence": [max(m.similarity, 0.0) for m in matches],
            "Technologies": [by_id[m.candidat_id].get("technologies") or [] for m in matches],
        }
    )
    selected_id = _selectable_table(
        table,
        ["Candidat", "Poste", "Expérience (ans)", "Pertinence", "Technologies"],
        {
            "Pertinence": st.column_config.ProgressColumn(
                min_value=0.0, max_value=1.0, format="percent", help="Similarité cosinus entre la requête et le profil"
            ),
            "Technologies": st.column_config.ListColumn(width="large"),
        },
        key=f"semantique_table_{hash((query, experience))}",
    )
    _render_selected_fiche(selected_id, key="semantique_fiche")


def _render_backfill() -> bool:
    """Propose de calculer les embeddings manquants ; retourne False si la lecture échoue."""
    try:
        missing = db.list_candidats_sans_embedding()
    except Exception as exc:  # noqa: BLE001
        st.error(f"Lecture des embeddings impossible : {exc}")
        return False

    if missing:
        info, action = st.columns([3, 1], vertical_alignment="center")
        info.warning(f"{len(missing)} CV analysé(s) sans embedding : ils n'apparaissent pas dans cette recherche.")
        if action.button("Calculer les embeddings", key="semantique_rattrapage"):
            progress = st.progress(0.0, text="Chargement du modèle…")
            done, errors = backfill_embeddings(
                on_progress=lambda index, total: progress.progress(
                    (index - 1) / total, text=f"Embedding {index}/{total}"
                )
            )
            progress.empty()
            st.session_state["semantique_rattrapage_erreurs"] = errors
            st.toast(f"{done} embedding(s) calculé(s).")
            st.rerun()

    for error in st.session_state.pop("semantique_rattrapage_erreurs", []):
        st.error(error)
    return True


# --- Commun ---

def _render_experience_filter(key: str, min_column: Any, max_column: Any) -> ExperienceFilter | None:
    """Champs min / max d'expérience ; retourne None si min > max."""
    bounds = {"min_value": 0.0, "max_value": float(MAX_EXPERIENCE_YEARS), "value": None, "step": 1.0}
    minimum = min_column.number_input("Expérience min. (ans)", key=f"{key}_experience_min", **bounds)
    maximum = max_column.number_input("Expérience max. (ans)", key=f"{key}_experience_max", **bounds)
    has_filter = minimum is not None or maximum is not None
    include_unknown = st.checkbox(
        "Inclure les candidats dont l'expérience est inconnue",
        disabled=not has_filter,
        key=f"{key}_experience_inconnue",
    )

    if minimum is not None and maximum is not None and minimum > maximum:
        st.error("L'expérience minimale est supérieure à l'expérience maximale.")
        return None
    return ExperienceFilter(minimum, maximum, include_unknown and has_filter)


def _selectable_table(
    table: pd.DataFrame, columns: list[str], column_config: dict[str, Any], *, key: str
) -> str | None:
    """Tableau à sélection unique ; retourne l'id de la ligne choisie."""
    event = st.dataframe(
        table,
        column_order=columns,
        column_config={"Expérience (ans)": st.column_config.NumberColumn(format="%.1f"), **column_config},
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        # La clé change avec la recherche : une sélection ne doit pas survivre à de nouveaux résultats
        key=key,
    )
    rows = event.selection.rows
    return str(table.iloc[rows[0]]["id"]) if rows else None


def _render_selected_fiche(candidat_id: str | None, *, key: str) -> None:
    if candidat_id is None:
        st.caption("Sélectionnez une ligne pour afficher la fiche du candidat.")
        return
    render_fiche_by_id(candidat_id, key=key)
