"""Turning raw ENA report rows into the generated models."""

from __future__ import annotations

from typing import Any, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


def _coerce(record: dict[str, Any], model_cls: type[T]) -> T:
    """Build a model instance from a flat report dict, trying common key aliases.

    Any raw key that doesn't map to a known field is passed through unchanged
    (relies on the model's ``extra="allow"`` config to keep it in
    ``model_dump()``), so a Reports API field name the alias table doesn't yet
    anticipate is still visible to callers instead of silently dropped.
    """
    aliases: dict[str, tuple[str, ...]] = getattr(model_cls, "ALIASES", {})
    field_names = set(model_cls.model_fields.keys())
    # Keys reserved for other typed fields this model declares (e.g. an
    # ExperimentReport row's "studyAccession" foreign key) — the generic
    # "accession" field must not steal one of these just because it appears
    # earlier in its own alias tuple than this record's own entity-typed key
    # (e.g. "experimentAccession").
    reserved_keys: set[str] = set()
    for field in field_names:
        if field != "accession":
            reserved_keys.update(aliases.get(field, ()))

    out: dict[str, Any] = {}
    consumed_keys: set[str] = set()
    for field in field_names:
        candidates = aliases.get(field, (field,))
        if field == "accession":
            candidates = tuple(k for k in candidates if k not in reserved_keys)
        for key in candidates:
            if key in record and record[key] not in (None, ""):
                out[field] = record[key]
                consumed_keys.add(key)
                break
    for key, value in record.items():
        if key not in consumed_keys and key not in out:
            out[key] = value
    return model_cls.model_validate(out)
