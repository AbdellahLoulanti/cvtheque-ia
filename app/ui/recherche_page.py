"""Page Recherche : filtres multicritères et résultats avec critères trouvés / manquants."""

from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from app import db
from app.config import MAX_EXPERIENCE_YEARS, STATUT_ANALYSE, is_supabase_configured
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


def render() -> None:
    st.header("Recherche")
    st.caption("Combinez compétences, technologies, poste et expérience. La casse et les accents sont ignorés.")

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

    selected_id = _render_results(results, criteria)
    if selected_id is None:
        st.caption("Sélectionnez une ligne pour afficher la fiche du candidat.")
        return
    render_fiche_by_id(selected_id)


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
    experience_min = min_column.number_input(
        "Expérience min. (ans)", min_value=0.0, max_value=float(MAX_EXPERIENCE_YEARS), value=None, step=1.0
    )
    experience_max = max_column.number_input(
        "Expérience max. (ans)", min_value=0.0, max_value=float(MAX_EXPERIENCE_YEARS), value=None, step=1.0
    )
    has_experience_filter = experience_min is not None or experience_max is not None
    include_unknown = st.checkbox(
        "Inclure les candidats dont l'expérience est inconnue",
        disabled=not has_experience_filter,
    )

    if experience_min is not None and experience_max is not None and experience_min > experience_max:
        st.error("L'expérience minimale est supérieure à l'expérience maximale.")
        return None

    return SearchCriteria(
        # Un terme saisi « Java + Spring » compte pour deux critères
        terms=dedupe_terms(term for entry in selected for term in parse_terms(entry)),
        mode=mode,
        poste=poste,
        experience_min=experience_min,
        experience_max=experience_max,
        include_unknown_experience=include_unknown and has_experience_filter,
    )


def _render_results(results: list[SearchResult], criteria: SearchCriteria) -> str | None:
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

    event = st.dataframe(
        table,
        column_order=columns,
        column_config={
            "Expérience (ans)": st.column_config.NumberColumn(format="%.1f"),
            "Termes": st.column_config.TextColumn(help="Compétences / technologies trouvées sur le total demandé"),
            "Critères trouvés": st.column_config.ListColumn(width="large"),
            "Critères manquants": st.column_config.ListColumn(),
            "À vérifier": st.column_config.ListColumn(),
        },
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        # Nouvelle clé à chaque recherche : une sélection ne doit pas survivre à un changement de résultats
        key=f"recherche_table_{hash(criteria)}",
    )

    rows = event.selection.rows
    return str(table.iloc[rows[0]]["id"]) if rows else None
