"""Point d'entrée Streamlit — CVthèque IA."""

from __future__ import annotations

import streamlit as st

from app.config import is_groq_configured
from app.db import test_connection

PAGES = ("Import", "Candidats", "Recherche", "AO & Matching")


def _sidebar_status() -> str:
    st.sidebar.title("CVthèque IA")
    st.sidebar.markdown("---")

    if is_groq_configured():
        st.sidebar.success("Clé API chargée")
    else:
        st.sidebar.error("Clé API manquante")

    result = test_connection()
    if result["ok"]:
        st.sidebar.success("Supabase connecté")
    else:
        st.sidebar.error("Supabase non connecté")
        st.sidebar.caption(result["message"])

    st.sidebar.markdown("---")
    return st.sidebar.radio("Navigation", PAGES, label_visibility="collapsed")


def page_import() -> None:
    st.header("Import")
    st.info("Import de CV (PDF / DOCX) — à venir.")


def page_candidats() -> None:
    st.header("Candidats")
    st.info("Liste et détail des candidats — à venir.")


def page_recherche() -> None:
    st.header("Recherche")
    st.info("Recherche sémantique dans la CVthèque — à venir.")


def page_ao_matching() -> None:
    st.header("AO & Matching")
    st.info("Appels d'offres et matching candidats — à venir.")


def main() -> None:
    st.set_page_config(
        page_title="CVthèque IA",
        page_icon="📄",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    page = _sidebar_status()

    if page == "Import":
        page_import()
    elif page == "Candidats":
        page_candidats()
    elif page == "Recherche":
        page_recherche()
    else:
        page_ao_matching()


if __name__ == "__main__":
    main()
