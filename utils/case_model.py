"""Datos del caso clínico anonimizado.

La interfaz y el informe PDF comparten una única estructura para los datos
del caso: identificador anonimizado, edad, fecha del estudio ecográfico,
lado y notas de los hallazgos ecográficos.

No se admiten datos identificativos del paciente (nombre, documento de
identidad o número de historia clínica). El identificador es un código
libre que introduce el usuario y se normaliza a texto plano antes de
almacenarse en memoria.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

SIDE_UNSPECIFIED = "No especificado"
SIDE_LEFT = "Izquierdo"
SIDE_RIGHT = "Derecho"

SIDE_OPTIONS: tuple[str, ...] = (SIDE_UNSPECIFIED, SIDE_LEFT, SIDE_RIGHT)

MIN_AGE = 18
MAX_AGE = 100
MAX_IDENTIFIER_LENGTH = 64
MAX_NOTES_LENGTH = 1200

_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")
_SPACES = re.compile(r"\s+")


@dataclass(frozen=True)
class CaseData:
    """Datos anonimizados de un caso clínico evaluado."""

    identifier: str
    age: int
    study_date: date
    side: str
    notes: str

    @property
    def display_identifier(self) -> str:
        """Identificador mostrado en el informe (nunca vacío)."""

        return self.identifier or "Sin identificador"

    @property
    def has_notes(self) -> bool:
        return bool(self.notes.strip())


def sanitize_identifier(value: object) -> str:
    """Normaliza el identificador anonimizado a texto plano y compacto."""

    if value is None:
        return ""
    text = _CONTROL_CHARS.sub(" ", str(value))
    text = _SPACES.sub(" ", text).strip()
    return text[:MAX_IDENTIFIER_LENGTH]


def sanitize_notes(value: object) -> str:
    """Normaliza las notas de hallazgos ecográficos."""

    if value is None:
        return ""
    text = _CONTROL_CHARS.sub(" ", str(value)).strip()
    return text[:MAX_NOTES_LENGTH]


def validate_age(value: object) -> int:
    """Valida la edad de la paciente (18-100 años)."""

    if isinstance(value, bool):
        raise ValueError("La edad debe ser un número entero.")
    try:
        age = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("La edad debe ser un número entero.") from exc
    if not MIN_AGE <= age <= MAX_AGE:
        raise ValueError(f"La edad debe estar entre {MIN_AGE} y {MAX_AGE} años.")
    return age


def validate_side(value: object) -> str:
    """Valida el lado de la masa anexial."""

    if value not in SIDE_OPTIONS:
        raise ValueError(
            f"Lado no válido: {value}. Opciones: {', '.join(SIDE_OPTIONS)}."
        )
    return str(value)


def validate_study_date(value: object) -> date:
    """Valida la fecha del estudio ecográfico (no futura)."""

    if not isinstance(value, date):
        raise ValueError("La fecha del estudio ecográfico no es válida.")
    if value > date.today():
        raise ValueError(
            "La fecha del estudio ecográfico no puede ser posterior a hoy."
        )
    return value


def build_case_data(
    *,
    identifier: object = "",
    age: object,
    study_date: object,
    side: object = SIDE_UNSPECIFIED,
    notes: object = "",
) -> CaseData:
    """Construye y valida los datos del caso.

    Raises:
        ValueError: Si algún valor está fuera del rango o formato admitido.
    """

    return CaseData(
        identifier=sanitize_identifier(identifier),
        age=validate_age(age),
        study_date=validate_study_date(study_date),
        side=validate_side(side),
        notes=sanitize_notes(notes),
    )


__all__ = [
    "CaseData",
    "MAX_AGE",
    "MAX_IDENTIFIER_LENGTH",
    "MAX_NOTES_LENGTH",
    "MIN_AGE",
    "SIDE_LEFT",
    "SIDE_OPTIONS",
    "SIDE_RIGHT",
    "SIDE_UNSPECIFIED",
    "build_case_data",
    "sanitize_identifier",
    "sanitize_notes",
    "validate_age",
    "validate_side",
    "validate_study_date",
]
