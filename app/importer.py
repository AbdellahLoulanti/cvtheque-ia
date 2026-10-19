"""Import en lot des CV : extraction, contrôles, Storage et création des candidats."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Callable, Iterable

from app import db
from app.config import ACCEPTED_CV_TYPES
from app.extraction import ExtractionError, clean_text, extract_text, has_usable_text


class ImportStatus(str, Enum):
    IMPORTED = "Importé"
    DUPLICATE = "Doublon"
    REJECTED = "Rejeté"
    ERROR = "Erreur"


@dataclass
class ImportResult:
    filename: str
    status: ImportStatus
    message: str
    candidat_id: str | None = None


ProgressCallback = Callable[[int, int, str], None]


def storage_path(filename: str) -> str:
    """Nom de fichier compatible avec les clés du Storage Supabase (ASCII, sans espaces)."""
    path = Path(filename)
    stem = unicodedata.normalize("NFKD", path.stem).encode("ascii", "ignore").decode()
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", stem).strip("._") or "cv"
    return f"{stem}{path.suffix.lower()}"


def import_cvs(
    files: Iterable[tuple[str, bytes]],
    on_progress: ProgressCallback | None = None,
) -> list[ImportResult]:
    """Importe chaque fichier (nom, contenu) et retourne un rapport par fichier."""
    files = list(files)
    results: list[ImportResult] = []
    seen_paths: set[str] = set()

    for index, (filename, data) in enumerate(files, start=1):
        if on_progress:
            on_progress(index, len(files), filename)
        results.append(_import_one(filename, data, seen_paths))

    return results


def _import_one(filename: str, data: bytes, seen_paths: set[str]) -> ImportResult:
    ext = Path(filename).suffix.lower()
    content_type = ACCEPTED_CV_TYPES.get(ext)
    if content_type is None:
        return ImportResult(filename, ImportStatus.REJECTED, f"Format non supporté ({ext or 'aucune extension'})")

    path = storage_path(filename)
    if path in seen_paths:
        return ImportResult(filename, ImportStatus.DUPLICATE, "Fichier déjà présent dans ce lot")
    seen_paths.add(path)

    try:
        if db.candidat_exists(path):
            return ImportResult(filename, ImportStatus.DUPLICATE, "Un CV avec ce nom existe déjà dans la CVthèque")
    except Exception as exc:  # noqa: BLE001
        return ImportResult(filename, ImportStatus.ERROR, f"Vérification des doublons impossible : {exc}")

    try:
        text = clean_text(extract_text(filename, data))
    except ExtractionError as exc:
        return ImportResult(filename, ImportStatus.REJECTED, str(exc))

    if not has_usable_text(text):
        reason = "PDF scanné ou sans couche texte" if ext == ".pdf" else "Fichier vide ou sans texte exploitable"
        return ImportResult(filename, ImportStatus.REJECTED, reason)

    try:
        # Aucun candidat ne référence ce chemin (vérifié plus haut) : un fichier déjà
        # présent est orphelin, par exemple après suppression de la ligne dans Supabase
        db.upload_cv(path, data, content_type, overwrite=True)
    except Exception as exc:  # noqa: BLE001
        return ImportResult(filename, ImportStatus.ERROR, f"Envoi vers le Storage impossible : {exc}")

    try:
        candidat = db.insert_candidat({"texte_brut": text, "chemin_fichier": path})
    except Exception as exc:  # noqa: BLE001
        try:
            db.delete_cv(path)
        except Exception:  # noqa: BLE001 — l'erreur d'origine prime
            pass
        return ImportResult(filename, ImportStatus.ERROR, f"Création du candidat impossible : {exc}")

    return ImportResult(
        filename,
        ImportStatus.IMPORTED,
        f"{len(text):,} caractères extraits".replace(",", " "),
        candidat_id=candidat.get("id"),
    )
