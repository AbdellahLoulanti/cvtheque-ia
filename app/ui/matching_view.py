"""Affichage du matching AO ↔ candidats : classement, détail du score et comparaison côte à côte."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pandas as pd
import streamlit as st

from app import db
from app.matching import (
    SKILL_CREDIT,
    WEIGHTS,
    Criterion,
    MatchResult,
    SkillMatch,
    SkillStatus,
    criterion_gaps,
    format_number,
)
from app.ui.fiche import display_name, escape_markdown, render_file_link

_SHORT_LABELS = {
    Criterion.REQUIRED: "Obligatoires",
    Criterion.DESIRED: "Souhaitées",
    Criterion.EXPERIENCE: "Expérience",
    Criterion.SEMANTIC: "Sémantique",
}
_STATUS_COLORS = {SkillStatus.ACQUIRED: "green", SkillStatus.UNPROVEN: "orange", SkillStatus.MISSING: "red"}


def render_ranking(ao: Mapping[str, Any], results: list[MatchResult]) -> None:
    """Classement des candidats par score, puis détail du candidat sélectionné."""
    _render_scoring_rules()
    if not results:
        st.info("Aucun CV analysé à comparer : importez et analysez des CV depuis la page Import.")
        return

    table = pd.DataFrame(
        {
            "id": [r.candidat["id"] for r in results],
            "Rang": range(1, len(results) + 1),
            "Candidat": [display_name(r.candidat) for r in results],
            "Poste": [r.candidat.get("poste") for r in results],
            "Score": [r.score for r in results],
            **{
                _column(c): [r.criterion(c).points for r in results]
                for c in Criterion
            },
            "Obligatoires manquantes": [[_gap_label(m) for m in r.gaps] for r in results],
        }
    )
    event = st.dataframe(
        table,
        column_order=["Rang", "Candidat", "Poste", "Score", *map(_column, Criterion), "Obligatoires manquantes"],
        column_config={
            "Score": st.column_config.ProgressColumn(min_value=0.0, max_value=100.0, format="%.1f %%"),
            **{
                _column(c): st.column_config.NumberColumn(format="%.1f", help=f"{c.value} : sur {WEIGHTS[c]} points")
                for c in Criterion
            },
            "Obligatoires manquantes": st.column_config.ListColumn(width="large"),
        },
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        key=f"matching_table_{ao['id']}",
    )

    rows = event.selection.rows
    if not rows:
        st.caption("Sélectionnez un candidat pour afficher le détail de son score.")
        return
    render_match_detail(results[rows[0]], rank=rows[0] + 1, key="matching_detail")


def render_match_detail(result: MatchResult, *, rank: int, key: str, compact: bool = False) -> None:
    """Détail d'un candidat ; `compact` (comparaison) omet le tableau de calcul, déjà résumé à côté."""
    with st.container(border=True):
        title, score = st.columns([3, 1], vertical_alignment="center")
        title.markdown(f"### {rank}. {escape_markdown(display_name(result.candidat))}")
        poste = result.candidat.get("poste")
        title.markdown(escape_markdown(poste) if poste else "*Poste non renseigné*")
        score.metric("Score", f"{format_number(result.score)} %")

        if compact:
            _render_strengths(result)
            _render_gaps(result)
        else:
            st.markdown("**Détail du score**")
            _render_score_table(result)
            strengths, gaps = st.columns(2, gap="large")
            with strengths:
                _render_strengths(result)
            with gaps:
                _render_gaps(result)

        _render_skill_badges("Compétences obligatoires de l'AO", result.required)
        _render_skill_badges("Compétences souhaitées de l'AO", result.desired)
        render_file_link(
            result.candidat.get("chemin_fichier"),
            db.create_cv_signed_url,
            label="Ouvrir le CV original",
            key=f"{key}_cv",
        )


def render_comparison(ao: Mapping[str, Any], results: list[MatchResult]) -> None:
    """Deux candidats côte à côte, avec l'écart de points critère par critère."""
    if len(results) < 2:
        st.info("Il faut au moins deux CV analysés pour comparer des candidats.")
        return

    by_id = {str(r.candidat["id"]): (rank, r) for rank, r in enumerate(results, start=1)}
    options = list(by_id)

    def label(candidat_id: str) -> str:
        rank, result = by_id[candidat_id]
        return f"{rank}. {display_name(result.candidat)} — {format_number(result.score)} %"

    left, right = st.columns(2)
    id_a = left.selectbox("Candidat A", options, index=0, format_func=label, key=f"comparaison_a_{ao['id']}")
    id_b = right.selectbox("Candidat B", options, index=1, format_func=label, key=f"comparaison_b_{ao['id']}")
    if id_a == id_b:
        st.warning("Choisissez deux candidats différents.")
        return

    (rank_a, a), (rank_b, b) = by_id[id_a], by_id[id_b]
    name_a, name_b = display_name(a.candidat), display_name(b.candidat)
    if name_a == name_b:
        name_a, name_b = f"{name_a} (A)", f"{name_b} (B)"

    rows = [
        {
            "Critère": f"{c.value} (/{WEIGHTS[c]})",
            name_a: a.criterion(c).points,
            name_b: b.criterion(c).points,
            "Écart (A − B)": round(a.criterion(c).points - b.criterion(c).points, 1),
        }
        for c in Criterion
    ]
    rows.append(
        {"Critère": "Score total (/100)", name_a: a.score, name_b: b.score, "Écart (A − B)": round(a.score - b.score, 1)}
    )
    st.dataframe(
        pd.DataFrame(rows),
        hide_index=True,
        column_config={
            name_a: st.column_config.NumberColumn(format="%.1f"),
            name_b: st.column_config.NumberColumn(format="%.1f"),
            "Écart (A − B)": st.column_config.NumberColumn(format="%+.1f"),
        },
    )
    st.markdown(_explain_gap(a, b, name_a, name_b))

    for column, rank, result, key in ((left, rank_a, a, "comparaison_a"), (right, rank_b, b, "comparaison_b")):
        with column:
            render_match_detail(result, rank=rank, key=key, compact=True)


def _render_scoring_rules() -> None:
    weights = " + ".join(f"{_SHORT_LABELS[c].lower()} {WEIGHTS[c]}" for c in Criterion)
    st.caption(
        f"Score sur 100 = {weights} points. Compétence acquise (dans la fiche) = "
        f"{format_number(SKILL_CREDIT[SkillStatus.ACQUIRED])}, non démontrée (seulement dans le texte du CV) = "
        f"{format_number(SKILL_CREDIT[SkillStatus.UNPROVEN])}, manquante = 0. "
        "Un critère que l'AO ne précise pas rapporte tous ses points. Points arrondis au dixième."
    )


def _render_score_table(result: MatchResult) -> None:
    rows = [
        {
            "Critère": c.criterion.value,
            "Calcul": c.formula,
            "Points": c.points,
            "Sur": c.weight,
            "Explication": c.detail,
        }
        for c in result.criteria
    ]
    rows.append(
        {
            "Critère": "Total",
            "Calcul": " + ".join(format_number(c.points) for c in result.criteria),
            "Points": result.score,
            "Sur": 100,
            "Explication": "Somme des points des quatre critères",
        }
    )
    st.dataframe(
        pd.DataFrame(rows),
        hide_index=True,
        column_config={
            "Points": st.column_config.NumberColumn(format="%.1f"),
            "Explication": st.column_config.TextColumn(width="large"),
        },
    )


def _render_strengths(result: MatchResult) -> None:
    st.markdown("**Points forts**")
    if result.strengths:
        st.success("\n".join(f"- {escape_markdown(s)}" for s in result.strengths))
    else:
        st.caption("Aucun point fort marquant pour cet AO.")


def _render_gaps(result: MatchResult) -> None:
    st.markdown("**Compétences obligatoires manquantes ou non démontrées**")
    if not result.required:
        st.caption("L'AO ne précise pas de compétences obligatoires.")
    elif result.gaps:
        lines = []
        for match in result.gaps:
            reason = (
                "citée dans le CV mais absente de la fiche, à vérifier en entretien"
                if match.status is SkillStatus.UNPROVEN
                else "introuvable dans le CV"
            )
            lines.append(f"- **{escape_markdown(match.skill)}** : {match.status.value.lower()} ({reason})")
        st.warning("\n".join(lines))
    else:
        st.success("Toutes les compétences obligatoires sont acquises.")


def _render_skill_badges(label: str, matches: tuple[SkillMatch, ...]) -> None:
    if not matches:
        return
    badges = []
    for match in matches:
        text = match.skill
        if match.evidence and match.evidence.casefold() != match.skill.casefold():
            text += f" ({match.evidence})"
        badges.append(f":{_STATUS_COLORS[match.status]}-badge[{escape_markdown(text)}]")
    legend = " · ".join(f":{_STATUS_COLORS[s]}[{s.value}]" for s in SkillStatus)
    st.markdown(f"**{label}** — {legend}")
    st.markdown(" ".join(badges))


def _explain_gap(a: MatchResult, b: MatchResult, name_a: str, name_b: str) -> str:
    """Phrase expliquant l'écart de score par les critères qui pèsent le plus."""
    difference = round(a.score - b.score, 1)
    if difference == 0:
        return "Les deux candidats ont le même score."

    leader, other = (name_a, name_b) if difference > 0 else (name_b, name_a)
    sign = 1 if difference > 0 else -1
    gaps = [(c, sign * gap) for c, gap in criterion_gaps(a, b)]
    ahead = [f"{c.value.lower()} (+{format_number(gap)} pts)" for c, gap in gaps if gap > 0]
    behind = [f"{c.value.lower()} (+{format_number(-gap)} pts)" for c, gap in gaps if gap < 0]

    text = (
        f"**{escape_markdown(leader)}** devance **{escape_markdown(other)}** de "
        f"**{format_number(abs(difference))} points**, grâce à : {escape_markdown(', '.join(ahead))}."
    )
    if behind:
        text += f" {escape_markdown(other)} reprend l'avantage sur : {escape_markdown(', '.join(behind))}."
    return text


def _column(criterion: Criterion) -> str:
    return f"{_SHORT_LABELS[criterion]} /{WEIGHTS[criterion]}"


def _gap_label(match: SkillMatch) -> str:
    return match.skill if match.status is SkillStatus.MISSING else f"{match.skill} (non démontrée)"
