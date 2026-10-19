"""Point d'entrée Streamlit — CVthèque IA."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from app.config import ACCEPTED_CV_EXTENSIONS, is_groq_configured, is_supabase_configured
from app.db import test_connection
from app.importer import ImportResult, ImportStatus, import_cvs

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
    st.caption("Formats acceptés : PDF, DOCX, TXT. Vous pouvez sélectionner plusieurs fichiers.")

    if not is_supabase_configured():
        st.error("Supabase n'est pas configuré : renseignez SUPABASE_URL et SUPABASE_KEY dans .env.")
        return

    files = st.file_uploader(
        "CV à importer",
        type=[ext.lstrip(".") for ext in ACCEPTED_CV_EXTENSIONS],
        accept_multiple_files=True,
    )

    if st.button("Importer", type="primary", disabled=not files):
        progress = st.progress(0.0)

        def on_progress(index: int, total: int, filename: str) -> None:
            progress.progress((index - 1) / total, text=f"{index}/{total} — {filename}")

        results = import_cvs(((f.name, f.getvalue()) for f in files), on_progress=on_progress)
        progress.empty()
        st.session_state["import_results"] = results

    results = st.session_state.get("import_results")
    if results:
        _render_import_report(results)


def _render_import_report(results: list[ImportResult]) -> None:
    st.subheader("Rapport d'import")

    counts = {status: sum(r.status is status for r in results) for status in ImportStatus}
    for column, status in zip(st.columns(len(ImportStatus)), ImportStatus):
        column.metric(status.value, counts[status])

    report = pd.DataFrame(
        [{"Fichier": r.filename, "Statut": r.status.value, "Détail": r.message} for r in results]
    )
    st.dataframe(report, hide_index=True)


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
