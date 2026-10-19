"""Appels Groq avec sortie JSON imposée par un schéma et nouvel essai automatique."""

from __future__ import annotations

import json
import time
from typing import Any, Callable

from groq import APIConnectionError, BadRequestError, Groq, InternalServerError, RateLimitError

from app.config import (
    GROQ_API_KEY,
    GROQ_MAX_ATTEMPTS,
    GROQ_MAX_WAIT_SECONDS,
    GROQ_MODEL,
    is_groq_configured,
)

# Appelé avant chaque attente : (secondes, numéro de l'essai suivant, raison)
WaitCallback = Callable[[float, int, str], None]


class LLMError(Exception):
    """Échec définitif de l'appel au LLM."""


class QuotaExhaustedError(LLMError):
    """Quota Groq épuisé pour une durée trop longue pour attendre (ex. quota journalier)."""


_client: Groq | None = None


def get_groq() -> Groq:
    global _client
    if not is_groq_configured():
        raise LLMError("Clé Groq manquante : renseigner GROQ_API_KEY dans .env")
    if _client is None:
        # Les nouveaux essais sont gérés ici pour pouvoir informer l'interface
        _client = Groq(api_key=GROQ_API_KEY, max_retries=0)
    return _client


def complete_json(
    system_prompt: str,
    user_prompt: str,
    schema_name: str,
    schema: dict[str, Any],
    on_wait: WaitCallback | None = None,
) -> dict[str, Any]:
    """Retourne la réponse du modèle, conforme au schéma JSON fourni."""
    client = get_groq()

    for attempt in range(1, GROQ_MAX_ATTEMPTS + 1):
        try:
            completion = client.chat.completions.create(
                model=GROQ_MODEL,
                temperature=0,
                reasoning_effort="low",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                response_format={
                    "type": "json_schema",
                    "json_schema": {"name": schema_name, "strict": True, "schema": schema},
                },
            )
            return json.loads(completion.choices[0].message.content or "")
        except RateLimitError as exc:
            delay = _retry_after(exc, attempt)
            if delay > GROQ_MAX_WAIT_SECONDS:
                raise QuotaExhaustedError(
                    f"Quota Groq épuisé, réessayez dans {_format_duration(delay)}"
                ) from exc
            reason = "Limite de requêtes Groq atteinte"
            error: Exception = exc
        except (APIConnectionError, InternalServerError) as exc:
            delay, reason, error = _backoff(attempt), "Groq indisponible", exc
        except (BadRequestError, json.JSONDecodeError) as exc:
            # Le modèle n'a pas réussi à produire un JSON valide : nouvel essai
            if isinstance(exc, BadRequestError) and "json_validate_failed" not in str(exc):
                raise LLMError(f"Requête refusée par Groq : {exc}") from exc
            delay, reason, error = 1.0, "Réponse JSON invalide", exc

        if attempt == GROQ_MAX_ATTEMPTS:
            raise LLMError(f"{reason} après {GROQ_MAX_ATTEMPTS} essais : {error}") from error
        if on_wait:
            on_wait(delay, attempt + 1, reason)
        time.sleep(delay)

    raise AssertionError("unreachable")


def _retry_after(exc: RateLimitError, attempt: int) -> float:
    header = exc.response.headers.get("retry-after")
    try:
        return float(header) + 0.5
    except (TypeError, ValueError):
        return _backoff(attempt)


def _backoff(attempt: int) -> float:
    return min(2.0**attempt, 30.0)


def _format_duration(seconds: float) -> str:
    minutes, secs = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours} h {minutes:02d} min"
    if minutes:
        return f"{minutes} min {secs:02d} s"
    return f"{secs} s"
