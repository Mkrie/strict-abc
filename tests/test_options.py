"""Strict option inheritance and merging tests."""

from abc import abstractmethod
from collections.abc import Mapping
from typing import Any

import pytest

from strict_abc import (
    StrictABC,
)

# ===================================================================
# Options inheritance / merging
# ===================================================================


def test_options_inherited_from_base() -> None:
    class Base(StrictABC):
        __strict_options__ = {"check_names": True}

        @abstractmethod
        def m(self, alpha: int, /) -> int: ...

    with pytest.raises(TypeError, match="parameter name mismatch"):

        class _Impl(Base):
            def m(self, beta: int) -> int:
                return beta


def test_child_can_override_options() -> None:
    class Base(StrictABC):
        __strict_options__ = {"check_names": True}

        @abstractmethod
        def m(self, alpha: int, /) -> int: ...

    class Impl(Base):
        __strict_options__ = {"check_names": False}

        def m(self, beta: int) -> int:
            return beta

    assert Impl().m(1) == 1


def test_options_are_merged_from_base_classes() -> None:
    class Base(StrictABC):
        __strict_options__ = {"check_types": True}

        @abstractmethod
        def m(self, a: int) -> int: ...

    with pytest.raises(TypeError, match="type annotation mismatch"):

        class _Impl(Base):
            __strict_options__ = {"check_names": True}

            def m(self, a: str) -> int:
                return "x"


def test_options_mapping_non_dict_is_accepted() -> None:
    class OptionsMapping(Mapping):
        def __init__(self, data: dict[str, Any]) -> None:
            self._data = data

        def __getitem__(self, key: str) -> Any:
            return self._data[key]

        def __iter__(self) -> Any:
            return iter(self._data)

        def __len__(self) -> int:
            return len(self._data)

    class Base(StrictABC):
        __strict_options__ = OptionsMapping({"check_names": True})  # type: ignore[assignment]

        @abstractmethod
        def m(self, alpha: int, /) -> int: ...

    with pytest.raises(TypeError, match="parameter name mismatch"):

        class _Impl(Base):
            def m(self, beta: int) -> int:
                return beta


def test_options_non_mapping_is_ignored() -> None:
    class Base(StrictABC):
        __strict_options__ = object()  # type: ignore[assignment]

        @abstractmethod
        def m(self, a: int = 1) -> int: ...

    with pytest.raises(TypeError, match="removing default value"):

        class _Impl(Base):
            def m(self, a: int) -> int:
                return a


def test_invalid_strict_options_are_ignored() -> None:
    class Base(StrictABC):
        __strict_options__ = ["not-a-dict"]  # type: ignore[assignment]

        @abstractmethod
        def m(self, a: int = 1) -> int: ...

    with pytest.raises(TypeError, match="removing default value"):

        class _Impl(Base):
            def m(self, a: int) -> int:
                return a
