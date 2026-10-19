"""Fiche candidat réutilisable (pages Candidats, Recherche, AO & Matching)."""

from __future__ import annotations

import re
import string
from collections.abc import Mapping
from typing import Any

import streamlit as st

from app import db
from app.config import SIGNED_URL_EXPIRES_SECONDS, STATUT_ANALYSE, STATUT_ERREUR, STATUT_IMPORTE
from app.search import experience_years, format_years

FIELD_LABELS: dict[str, str] = {
    "nom": "Nom",
    "prenom": "Prénom",
    "email": "Email",
    "telephone": "Téléphone",
    "poste": "Poste",
    "experience_annees": "Expérience",
    "competences": "Compétences",
    "technologies": "Technologies",
    "formations": "Formations",
    "certifications": "Certifications",
    "langues": "Langues",
    "texte_brut": "Texte du CV",
}

STATUT_LABELS: dict[str, str] = {
    STATUT_IMPORTE: "Importé",
    STATUT_ANALYSE: "Analysé",
    STATUT_ERREUR: "Erreur d'analyse",
}
_STATUT_COLORS = {STATUT_IMPORTE: "gray", STATUT_ANALYSE: "green", STATUT_ERREUR: "red"}

# Toute ponctuation ASCII peut être échappée en Markdown ; « : » évite les émojis :nom:
_MARKDOWN_SPECIAL = re.compile(f"([{re.escape(string.punctuation)}])")


def escape_markdown(text: str) -> str:
    return _MARKDOWN_SPECIAL.sub(r"\\\1", text)


def display_name(candidat: Mapping[str, Any]) -> str:
    name = " ".join(part for part in (candidat.get("prenom"), candidat.get("nom")) if part)
    return name or candidat.get("chemin_fichier") or "Candidat sans nom"


def format_experience(years: float | None) -> str:
    return "Non renseignée" if years is None else format_years(years)


def render_fiche_by_id(candidat_id: str, *, show_texte: bool = True) -> None:
    """Charge le candidat depuis Supabase puis affiche sa fiche."""
    try:
        candidat = db.get_candidat(candidat_id)
    except Exception as exc:  # noqa: BLE001
        st.error(f"Lecture de la fiche impossible : {exc}")
        return
    if candidat is None:
        st.warning("Ce candidat n'existe plus.")
        return
    render_fiche(candidat, show_texte=show_texte)


def render_fiche(candidat: Mapping[str, Any], *, show_texte: bool = True) -> None:
    """Affiche la fiche complète d'un candidat (ligne de la table `candidats`)."""
    with st.container(border=True):
        _render_header(candidat)
        _render_identity(candidat)

        st.divider()
        left, right = st.columns(2, gap="large")
        with left:
            _render_tags("competences", candidat.get("competences"), "blue")
            _render_tags("technologies", candidat.get("technologies"), "violet")
        with right:
            _render_list("formations", candidat.get("formations"))
            _render_list("certifications", candidat.get("certifications"))
            _render_list("langues", candidat.get("langues"))

        st.divider()
        _render_incertitudes(candidat)
        _render_cv_link(candidat.get("chemin_fichier"))

        if show_texte:
            with st.expander("Texte extrait du CV"):
                texte = candidat.get("texte_brut")
                if texte:
                    st.code(texte, language=None, wrap_lines=True, height=400)
                else:
                    st.caption("Aucun texte extrait.")


def _render_header(candidat: Mapping[str, Any]) -> None:
    title, status = st.columns([4, 1], vertical_alignment="center")
    title.markdown(f"### {escape_markdown(display_name(candidat))}")
    poste = candidat.get("poste")
    title.markdown(escape_markdown(poste) if poste else "*Poste non renseigné*")

    statut = candidat.get("statut") or STATUT_IMPORTE
    color = _STATUT_COLORS.get(statut, "gray")
    status.markdown(f":{color}-badge[{escape_markdown(STATUT_LABELS.get(statut, statut))}]")


def _render_identity(candidat: Mapping[str, Any]) -> None:
    columns = st.columns(3)
    columns[0].metric(FIELD_LABELS["experience_annees"], format_experience(experience_years(candidat)))
    for column, field in zip(columns[1:], ("email", "telephone")):
        column.markdown(f"**{FIELD_LABELS[field]}**")
        value = candidat.get(field)
        if value:
            column.markdown(escape_markdown(value))
        else:
            column.caption("Non renseigné")


def _render_tags(field: str, values: list[str] | None, color: str) -> None:
    st.markdown(f"**{FIELD_LABELS[field]}**")
    if values:
        st.markdown(" ".join(f":{color}-badge[{escape_markdown(value)}]" for value in values))
    else:
        st.caption("Non renseigné")


def _render_list(field: str, values: list[str] | None) -> None:
    st.markdown(f"**{FIELD_LABELS[field]}**")
    if values:
        st.markdown("\n".join(f"- {escape_markdown(value)}" for value in values))
    else:
        st.caption("Non renseigné")


def _render_incertitudes(candidat: Mapping[str, Any]) -> None:
    if candidat.get("statut") != STATUT_ANALYSE:
        st.info("Ce CV n'a pas encore été analysé : lancez l'analyse IA depuis la page Import.")
        return

    incertitudes = candidat.get("incertitudes") or []
    if not incertitudes:
        st.success("Aucune incertitude signalée par l'analyse.")
        return

    lines = []
    for entry in incertitudes:
        field, sep, explanation = entry.partition(":")
        label = FIELD_LABELS.get(field.strip())
        if sep and label:
            lines.append(f"- **{label}** : {escape_markdown(explanation.strip())}")
        else:
            lines.append(f"- {escape_markdown(entry)}")
    st.warning(f"**Incertitudes ({len(incertitudes)})**\n\n" + "\n".join(lines))


def _render_cv_link(path: str | None) -> None:
    if not path:
        return
    try:
        url = db.create_cv_signed_url(path)
    except Exception as exc:  # noqa: BLE001
        st.error(f"CV original introuvable dans le Storage ({escape_markdown(path)}).")
        st.caption(escape_markdown(str(exc)))
        return
    st.link_button("Ouvrir le CV original", url, icon=":material/open_in_new:")
    st.caption(f"{escape_markdown(path)} — lien temporaire valable {SIGNED_URL_EXPIRES_SECONDS // 60} min.")
