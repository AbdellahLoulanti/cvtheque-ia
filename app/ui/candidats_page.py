"""Page Candidats : tableau récapitulatif et fiche détaillée du candidat sélectionné."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import pandas as pd
import streamlit as st

from app import db
from app.config import STATUT_ANALYSE, STATUT_ERREUR, STATUT_IMPORTE, is_supabase_configured
from app.ui.fiche import STATUT_LABELS, display_name, experience_years, render_fiche

_COLUMNS = ("Candidat", "Poste", "Expérience (ans)", "Technologies", "Langues", "Incertitudes", "Statut", "Importé le")


def render() -> None:
    st.header("Candidats")

    if not is_supabase_configured():
        st.error("Supabase n'est pas configuré : renseignez SUPABASE_URL et SUPABASE_KEY dans .env.")
        return

    try:
        candidats = db.list_candidats()
    except Exception as exc:  # noqa: BLE001
        st.error(f"Lecture des candidats impossible : {exc}")
        return

    if not candidats:
        st.info("Aucun candidat pour l'instant : importez des CV depuis la page Import.")
        return

    _render_counts(candidats)
    selected_id = _render_table(candidats)

    if selected_id is None:
        st.caption("Sélectionnez une ligne du tableau pour afficher la fiche du candidat.")
        return

    try:
        candidat = db.get_candidat(selected_id)
    except Exception as exc:  # noqa: BLE001
        st.error(f"Lecture de la fiche impossible : {exc}")
        return

    if candidat is None:
        st.warning("Ce candidat n'existe plus.")
        return
    render_fiche(candidat)


def _render_counts(candidats: list[dict[str, Any]]) -> None:
    statuts = [c.get("statut") for c in candidats]
    counts = {
        "Candidats": len(candidats),
        "Analysés": statuts.count(STATUT_ANALYSE),
        "En attente d'analyse": statuts.count(STATUT_IMPORTE),
        "En erreur": statuts.count(STATUT_ERREUR),
    }
    for column, (label, value) in zip(st.columns(len(counts)), counts.items()):
        column.metric(label, value)


def _render_table(candidats: list[dict[str, Any]]) -> str | None:
    """Affiche le tableau et retourne l'id du candidat sélectionné."""
    local_tz = datetime.now().astimezone().tzinfo
    table = pd.DataFrame(
        {
            "id": [c["id"] for c in candidats],
            "Candidat": [display_name(c) for c in candidats],
            "Poste": [c.get("poste") for c in candidats],
            "Expérience (ans)": [experience_years(c) for c in candidats],
            "Technologies": [c.get("technologies") or [] for c in candidats],
            "Langues": [c.get("langues") or [] for c in candidats],
            "Incertitudes": [len(c.get("incertitudes") or []) for c in candidats],
            "Statut": [STATUT_LABELS.get(c.get("statut"), c.get("statut")) for c in candidats],
            "Importé le": pd.to_datetime([c.get("created_at") for c in candidats], utc=True).tz_convert(local_tz),
        }
    )

    event = st.dataframe(
        table,
        column_order=_COLUMNS,
        column_config={
            "Expérience (ans)": st.column_config.NumberColumn(format="%.1f"),
            "Technologies": st.column_config.ListColumn(width="large"),
            "Langues": st.column_config.ListColumn(),
            "Incertitudes": st.column_config.NumberColumn(help="Nombre d'informations absentes ou incertaines"),
            "Importé le": st.column_config.DatetimeColumn(format="DD/MM/YYYY HH:mm"),
        },
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        key="candidats_table",
    )

    rows = event.selection.rows
    return str(table.iloc[rows[0]]["id"]) if rows else None
