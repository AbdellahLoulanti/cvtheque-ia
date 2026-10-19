"""Fiche appel d'offres : synthèse de l'AO et profil idéal."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from pathlib import PurePosixPath
from typing import Any

import pandas as pd
import streamlit as st

from app import db
from app.search import format_years
from app.ui.fiche import escape_markdown, render_file_link, render_incertitudes, render_list, render_tags

AO_FIELD_LABELS: dict[str, str] = {
    "titre": "Titre",
    "poste": "Poste recherché",
    "contexte": "Contexte",
    "responsabilites": "Responsabilités",
    "competences_obligatoires": "Compétences obligatoires",
    "competences_souhaitees": "Compétences souhaitées",
    "experience_requise": "Expérience requise",
    "experience_min_annees": "Expérience minimale",
    "technologies": "Technologies",
    "contraintes": "Contraintes",
    "profil_ideal": "Profil idéal",
    "texte_brut": "Texte de l'AO",
}


def format_date(value: str | None) -> str:
    """Horodatage Supabase (UTC) -> « 19/10/2026 17:55 » à l'heure locale."""
    if not value:
        return ""
    local_tz = datetime.now().astimezone().tzinfo
    return pd.to_datetime(value, utc=True).tz_convert(local_tz).strftime("%d/%m/%Y %H:%M")


def render_fiche_ao(ao: Mapping[str, Any], *, key: str = "fiche_ao") -> None:
    """Affiche la synthèse et le profil idéal d'un AO (ligne de la table `appels_offres`).

    `key` doit être unique par fiche affichée sur une même page.
    """
    with st.container(border=True):
        titre = ao.get("titre") or "Appel d'offres sans titre"
        st.markdown(f"### {escape_markdown(titre)}")
        poste = ao.get("poste")
        st.markdown(
            f"**{AO_FIELD_LABELS['poste']}** : {escape_markdown(poste)}" if poste else "*Poste recherché non précisé*"
        )
        _render_summary(ao)

        st.divider()
        left, right = st.columns(2, gap="large")
        with left:
            render_tags(AO_FIELD_LABELS["competences_obligatoires"], ao.get("competences_obligatoires"), "red")
            render_tags(AO_FIELD_LABELS["competences_souhaitees"], ao.get("competences_souhaitees"), "blue")
            render_tags(AO_FIELD_LABELS["technologies"], ao.get("technologies"), "violet")
        with right:
            render_list(AO_FIELD_LABELS["responsabilites"], ao.get("responsabilites"))
            render_list(AO_FIELD_LABELS["contraintes"], ao.get("contraintes"))

        st.divider()
        st.markdown(f"#### {AO_FIELD_LABELS['profil_ideal']}")
        profil = ao.get("profil_ideal")
        if profil:
            st.info(escape_markdown(profil), icon=":material/person_search:")
        else:
            st.caption("Profil idéal non généré.")

        render_incertitudes(ao.get("incertitudes") or [], AO_FIELD_LABELS)
        render_file_link(
            ao.get("chemin_fichier"), db.create_ao_signed_url, label="Ouvrir l'AO original", key=f"{key}_fichier"
        )

        with st.expander(AO_FIELD_LABELS["texte_brut"]):
            texte = ao.get("texte_brut")
            if texte:
                st.code(texte, language=None, wrap_lines=True, height=400)
            else:
                st.caption("Aucun texte enregistré.")


def _render_summary(ao: Mapping[str, Any]) -> None:
    years, requirement, source = st.columns(3)
    minimum = ao.get("experience_min_annees")
    years.metric(
        AO_FIELD_LABELS["experience_min_annees"], "Non précisée" if minimum is None else format_years(float(minimum))
    )

    requirement.markdown(f"**{AO_FIELD_LABELS['experience_requise']}**")
    if ao.get("experience_requise"):
        requirement.markdown(escape_markdown(ao["experience_requise"]))
    else:
        requirement.caption("Non précisée")

    source.markdown("**Source**")
    path = ao.get("chemin_fichier")
    origin = f"Fichier {PurePosixPath(path).name}" if path else "Texte collé"
    source.caption(escape_markdown(f"{origin} — analysé le {format_date(ao.get('created_at'))}"))

    if ao.get("contexte"):
        st.markdown(f"**{AO_FIELD_LABELS['contexte']}**")
        st.markdown(escape_markdown(ao["contexte"]))
