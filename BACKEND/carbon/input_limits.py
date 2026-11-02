"""Shared resource limits, applied before validating individual measurements."""
from typing import Annotated

from pydantic import BeforeValidator, StringConstraints
from pydantic_core import PydanticCustomError

MAX_MATERIAL_ENTRIES = 20
MAX_MATERIAL_NAME_LENGTH = 64
MAX_RAW_OCR_TEXT_LENGTH = 4000


def reject_too_many_materials(value):
    if isinstance(value, dict) and len(value) > MAX_MATERIAL_ENTRIES:
        raise PydanticCustomError("too_long",
            "Dictionary should have at most {max_length} items after validation, not {actual_length}",
            {"field_type": "Dictionary", "max_length": MAX_MATERIAL_ENTRIES,
             "actual_length": len(value)})
    return value


MaterialName = Annotated[str, StringConstraints(max_length=MAX_MATERIAL_NAME_LENGTH)]
RawOcrText = Annotated[str, StringConstraints(max_length=MAX_RAW_OCR_TEXT_LENGTH)]
