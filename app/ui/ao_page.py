"""Page AO & Matching : import et analyse IA d'un appel d'offres, fiche AO et profil idéal."""

from __future__ import annotations

from typing import Any

import streamlit as st

from app import db
from app.appels_offres import import_ao_file, import_ao_text
from app.config import ACCEPTED_AO_TYPES, is_groq_configured, is_supabase_configured
from app.ui.fiche_ao import format_date, render_fiche_ao_by_id

_SOURCES = ("Fichier", "Texte collé")
_SELECTION_KEY = "ao_selection"
# Change après chaque import réussi pour vider le fichier / texte saisi
_FORM_VERSION_KEY = "ao_form_version"


def render() -> None:
    st.header("AO & Matching")

    if not is_supabase_configured():
        st.error("Supabase n'est pas configuré : renseignez SUPABASE_URL et SUPABASE_KEY dans .env.")
        return

    try:
        appels_offres = db.list_appels_offres()
    except Exception as exc:  # noqa: BLE001
        st.error(f"Lecture des appels d'offres impossible : {exc}")
        return

    _render_import()
    st.divider()
    _render_appels_offres(appels_offres)


def _render_import() -> None:
    st.subheader("Nouvel appel d'offres")
    st.caption("Importez le fichier de l'AO ou collez son texte : l'IA en fait la synthèse et rédige le profil idéal.")

    if not is_groq_configured():
        st.warning("Clé Groq manquante : renseignez GROQ_API_KEY dans .env pour analyser un AO.")
        return

    version = st.session_state.setdefault(_FORM_VERSION_KEY, 0)
    source = st.radio("Source", _SOURCES, horizontal=True, key="ao_source")
    file, texte = None, ""
    if source == "Fichier":
        file = st.file_uploader(
            "Fichier de l'AO (PDF, DOCX, TXT)",
            type=[ext.lstrip(".") for ext in ACCEPTED_AO_TYPES],
            key=f"ao_fichier_{version}",
        )
    else:
        texte = st.text_area(
            "Texte de l'AO",
            height=250,
            placeholder="Collez ici le texte de l'appel d'offres…",
            key=f"ao_texte_{version}",
        )

    if st.button("Analyser l'AO", type="primary", disabled=file is None and not texte.strip()):
        waiting = st.empty()

        def on_wait(seconds: float, attempt: int, reason: str) -> None:
            waiting.info(f"{reason} : nouvel essai dans {seconds:.0f} s (essai {attempt}).")

        try:
            with st.spinner("Analyse de l'AO par l'IA…"):
                if file is not None:
                    imported = import_ao_file(file.name, file.getvalue(), on_wait=on_wait)
                else:
                    imported = import_ao_text(texte, on_wait=on_wait)
        except Exception as exc:  # noqa: BLE001
            waiting.empty()
            st.error(f"Analyse de l'AO impossible : {exc}")
            return

        st.session_state[_SELECTION_KEY] = imported.id
        st.session_state[_FORM_VERSION_KEY] = version + 1
        st.session_state["ao_import_message"] = imported
        st.rerun()

    imported = st.session_state.pop("ao_import_message", None)
    if imported is not None:
        st.success(f"AO « {imported.titre} » analysé et enregistré.")
        if imported.warning:
            st.warning(imported.warning)


def _render_appels_offres(appels_offres: list[dict[str, Any]]) -> None:
    st.subheader(f"Appels d'offres enregistrés ({len(appels_offres)})")
    if not appels_offres:
        st.info("Aucun appel d'offres pour l'instant : importez-en un ci-dessus.")
        return

    by_id = {str(ao["id"]): ao for ao in appels_offres}
    if st.session_state.get(_SELECTION_KEY) not in by_id:
        st.session_state.pop(_SELECTION_KEY, None)

    selected_id = st.selectbox(
        "Appel d'offres",
        list(by_id),
        format_func=lambda ao_id: f"{by_id[ao_id]['titre']} — {format_date(by_id[ao_id].get('created_at'))}",
        key=_SELECTION_KEY,
    )
    render_fiche_ao_by_id(selected_id)
