"""Configuration centralisée : variables d'environnement, modèles, formats."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# Racine du projet (parent de app/)
ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")

# --- Clés & services ---
GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "").strip()
SUPABASE_URL: str = os.getenv("SUPABASE_URL", "").strip()
SUPABASE_KEY: str = os.getenv("SUPABASE_KEY", "").strip()  # service_role côté serveur

# --- Modèles ---
EMBEDDING_MODEL: str = "paraphrase-multilingual-MiniLM-L12-v2"
EMBEDDING_DIM: int = 384
GROQ_MODEL: str = "openai/gpt-oss-120b"
GROQ_MAX_ATTEMPTS: int = 6
# Au-delà, la limite est un quota journalier : inutile de bloquer l'interface
GROQ_MAX_WAIT_SECONDS: float = 90.0

# --- Analyse IA ---
# Borne la taille d'une requête (quota gratuit Groq : 8 000 tokens / minute)
MAX_CV_CHARS_FOR_LLM: int = 12_000
MAX_EXPERIENCE_YEARS: int = 50

STATUT_IMPORTE = "importe"
STATUT_ANALYSE = "analyse"
STATUT_ERREUR = "erreur"

# --- Fichiers acceptés (extension -> type MIME pour le Storage) ---
ACCEPTED_CV_TYPES: dict[str, str] = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".txt": "text/plain",
}
ACCEPTED_CV_EXTENSIONS: tuple[str, ...] = tuple(ACCEPTED_CV_TYPES)

# En dessous de ce nombre de lettres, un CV est considéré sans texte exploitable
MIN_TEXT_LETTERS: int = 100

# --- Chemins locaux ---
DEMO_DATA_DIR = ROOT_DIR / "demo_data"
DATA_DIR = ROOT_DIR / "data"

# --- Storage Supabase ---
STORAGE_BUCKET_CVS = "cvs"


def is_groq_configured() -> bool:
    return bool(GROQ_API_KEY)


def is_supabase_configured() -> bool:
    return bool(SUPABASE_URL and SUPABASE_KEY)
