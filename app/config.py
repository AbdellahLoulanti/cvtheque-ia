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
GROQ_MODEL: str = "llama-3.3-70b-versatile"

# --- Fichiers acceptés ---
ACCEPTED_CV_EXTENSIONS: tuple[str, ...] = (".pdf", ".docx", ".doc", ".txt")
ACCEPTED_CV_MIME_TYPES: tuple[str, ...] = (
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/msword",
    "text/plain",
)

# --- Chemins locaux ---
DEMO_DATA_DIR = ROOT_DIR / "demo_data"
DATA_DIR = ROOT_DIR / "data"

# --- Storage Supabase ---
STORAGE_BUCKET_CVS = "cvs"


def is_groq_configured() -> bool:
    return bool(GROQ_API_KEY)


def is_supabase_configured() -> bool:
    return bool(SUPABASE_URL and SUPABASE_KEY)
