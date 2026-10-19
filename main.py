"""Point d'entrée Streamlit — CVthèque IA."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from app.analysis import LIST_FIELDS, AnalysisResult, AnalysisStatus, analyse_candidats
from app.config import ACCEPTED_CV_EXTENSIONS, is_groq_configured, is_supabase_configured
from app.db import list_candidats_a_analyser, test_connection
from app.importer import ImportResult, ImportStatus, import_cvs
from app.ui import candidats_page, recherche_page
from app.ui.fiche import FIELD_LABELS

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

    st.divider()
    _render_analysis_section()


def _render_import_report(results: list[ImportResult]) -> None:
    st.subheader("Rapport d'import")

    counts = {status: sum(r.status is status for r in results) for status in ImportStatus}
    for column, status in zip(st.columns(len(ImportStatus)), ImportStatus):
        column.metric(status.value, counts[status])

    report = pd.DataFrame(
        [{"Fichier": r.filename, "Statut": r.status.value, "Détail": r.message} for r in results]
    )
    st.dataframe(report, hide_index=True)


def _render_analysis_section() -> None:
    st.subheader("Analyse IA")

    if not is_groq_configured():
        st.warning("Clé Groq manquante : renseignez GROQ_API_KEY dans .env pour lancer l'analyse.")
        return

    include_analysed = st.checkbox("Réanalyser aussi les CV déjà analysés")
    try:
        pending = list_candidats_a_analyser(include_analysed=include_analysed)
    except Exception as exc:  # noqa: BLE001
        st.error(f"Lecture des candidats impossible : {exc}")
        return

    scope = "au total" if include_analysed else "en attente d'analyse (importés ou en erreur)"
    st.caption(f"{len(pending)} CV {scope}.")

    if st.button("Lancer l'analyse IA", type="primary", disabled=not pending):
        progress = st.progress(0.0)
        waiting = st.empty()

        def on_progress(index: int, total: int, filename: str) -> None:
            waiting.empty()
            progress.progress((index - 1) / total, text=f"Analyse {index}/{total} — {filename}")

        def on_wait(seconds: float, attempt: int, reason: str) -> None:
            waiting.info(f"{reason} : nouvel essai dans {seconds:.0f} s (essai {attempt}).")

        results = analyse_candidats(pending, on_progress=on_progress, on_wait=on_wait)
        st.session_state["analysis_results"] = results
        # Recharge la page pour mettre à jour le nombre de CV en attente
        st.rerun()

    results = st.session_state.get("analysis_results")
    if results:
        _render_analysis_report(results)


def _render_analysis_report(results: list[AnalysisResult]) -> None:
    counts = {status: sum(r.status is status for r in results) for status in AnalysisStatus}
    for column, status in zip(st.columns(len(AnalysisStatus)), AnalysisStatus):
        column.metric(status.value, counts[status])

    def join(values: list[str] | None) -> str:
        return ", ".join(values or [])

    rows = []
    for r in results:
        p = r.profile
        rows.append(
            {
                "Fichier": r.filename,
                "Statut": r.status.value,
                "Nom": p.get("nom"),
                "Prénom": p.get("prenom"),
                "Email": p.get("email"),
                "Téléphone": p.get("telephone"),
                "Poste": p.get("poste"),
                "Expérience (ans)": p.get("experience_annees"),
                **{FIELD_LABELS[name]: join(p.get(name)) for name in LIST_FIELDS},
                "Incertitudes": " · ".join(p.get("incertitudes", [])),
                "Détail": r.message,
            }
        )
    st.dataframe(pd.DataFrame(rows), hide_index=True)


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
        candidats_page.render()
    elif page == "Recherche":
        recherche_page.render()
    else:
        page_ao_matching()


if __name__ == "__main__":
    main()
