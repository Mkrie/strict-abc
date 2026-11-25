"""Annotation normalization and safety tests."""

import inspect
from pathlib import Path

import pytest

from strict_abc import (
    StrictABCMeta,
)

# ===================================================================
# Postponed annotations (PEP 563)
# ===================================================================


def test_postponed_annotations_return_covariance_allowed() -> None:
    code = (
        "from __future__ import annotations\n"
        "from abc import abstractmethod\n"
        "from strict_abc import StrictABC\n"
        "\n"
        "class Base(StrictABC):\n"
        "    __strict_options__ = {'check_return_type': True}\n"
        "\n"
        "    @abstractmethod\n"
        "    def m(self) -> object:\n"
        "        ...\n"
        "\n"
        "class Impl(Base):\n"
        "    def m(self) -> str:\n"
        "        return 'ok'\n"
    )
    exec(compile(code, "<string>", "exec"), {})


def test_postponed_annotations_invalid_return_raises() -> None:
    code = (
        "from __future__ import annotations\n"
        "from abc import abstractmethod\n"
        "from strict_abc import StrictABC\n"
        "\n"
        "class Base(StrictABC):\n"
        "    __strict_options__ = {'check_return_type': True}\n"
        "\n"
        "    @abstractmethod\n"
        "    def m(self) -> str:\n"
        "        ...\n"
        "\n"
        "class Impl(Base):\n"
        "    def m(self) -> object:\n"
        "        return object()\n"
    )
    with pytest.raises(TypeError, match="return type not covariant"):
        exec(compile(code, "<string>", "exec"), {})


# ===================================================================
# _normalize_annotation
# ===================================================================


def test_normalize_annotation_none() -> None:
    assert StrictABCMeta._normalize_annotation(None) is type(None)


def test_normalize_annotation_string_resolved() -> None:
    assert StrictABCMeta._normalize_annotation("int") is int


def test_normalize_annotation_string_unresolvable() -> None:
    result = StrictABCMeta._normalize_annotation("SomeUndefinedType")
    assert result == "SomeUndefinedType"


def test_normalize_annotation_empty_passthrough() -> None:
    assert (
        StrictABCMeta._normalize_annotation(inspect.Parameter.empty)
        is inspect.Parameter.empty
    )


def test_normalize_annotation_type_passthrough() -> None:
    assert StrictABCMeta._normalize_annotation(int) is int


def test_normalize_annotation_string_none() -> None:
    assert StrictABCMeta._normalize_annotation("None") is type(None)


def test_normalize_annotation_string_generic() -> None:
    assert StrictABCMeta._normalize_annotation("list[int]") == list[int]


def test_normalize_annotation_does_not_execute_builtin_functions(
    tmp_path: Path,
) -> None:
    target = tmp_path / "annotation.txt"
    annotations = [
        f"open({str(target)!r}, 'w').write('owned')",
        f"typing.__dict__['__builtins__']['open']({str(target)!r}, 'w')"
        f".write('owned')",
    ]

    for annotation in annotations:
        assert StrictABCMeta._normalize_annotation(annotation) == annotation
        assert not target.exists()
