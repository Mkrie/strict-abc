"""Calling-contract and signature validation tests."""

import inspect
from abc import abstractmethod
from typing import Any

import pytest

from strict_abc import (
    LSPViolation,
    StrictABC,
    StrictABCMeta,
)

# ===================================================================
# Valid implementations
# ===================================================================


def test_valid_concrete_subclass() -> None:
    class Base(StrictABC):
        @abstractmethod
        def m(self, a: int, b: int = 1) -> int: ...

    class Impl(Base):
        def m(self, a: int, b: int = 1) -> int:
            return a + b

    assert Impl().m(1) == 2
    assert Impl().m(1, 2) == 3


def test_adding_default_allowed() -> None:
    class Base(StrictABC):
        @abstractmethod
        def m(self, a: int) -> int: ...

    class Impl(Base):
        def m(self, a: int = 5) -> int:
            return a

    assert Impl().m() == 5


def test_adding_optional_parameter_without_variadic_allowed() -> None:
    class Base(StrictABC):
        @abstractmethod
        def m(self, a: int) -> int: ...

    class Impl(Base):
        def m(self, a: int, b: int = 0) -> int:
            return a + b

    assert Impl().m(1) == 1
    assert Impl().m(1, 2) == 3


# ===================================================================
# Default removal
# ===================================================================


def test_removing_default_raises() -> None:
    class Base(StrictABC):
        @abstractmethod
        def m(self, a: int, b: int = 1) -> int: ...

    with pytest.raises(TypeError, match="removing default value"):

        class _Impl(Base):
            def m(self, a: int, b: int) -> int:
                return a + b


def test_check_defaults_disabled_allows_removing_default() -> None:
    class Base(StrictABC):
        __strict_options__ = {"check_defaults": False}

        @abstractmethod
        def m(self, a: int = 1) -> int: ...

    class Impl(Base):
        def m(self, a: int) -> int:
            return a

    assert Impl().m(2) == 2


def test_check_defaults_disabled_allows_removing_keyword_only_default() -> None:
    class Base(StrictABC):
        __strict_options__ = {"check_defaults": False}

        @abstractmethod
        def m(self, *, a: int = 1) -> int: ...

    class Impl(Base):
        def m(self, *, a: int) -> int:
            return a

    assert Impl().m(a=2) == 2


def test_keyword_only_default_removal_by_name_raises() -> None:
    class Base(StrictABC):
        @abstractmethod
        def m(self, *, a: int = 1) -> int: ...

    with pytest.raises(TypeError, match="removing default value"):

        class _Impl(Base):
            def m(self, *, a: int) -> int:
                return a


# ===================================================================
# Required / extra parameters
# ===================================================================


def test_adding_required_parameter_without_variadic_raises() -> None:
    class Base(StrictABC):
        @abstractmethod
        def m(self, a: int) -> int: ...

    with pytest.raises(TypeError, match="new required parameter 'b'"):

        class _Impl(Base):
            def m(self, a: int, b: int) -> int:
                return a + b


def test_fewer_positional_parameters_raises() -> None:
    class Base(StrictABC):
        @abstractmethod
        def m(self, a: int, b: int) -> int: ...

    with pytest.raises(TypeError, match=r"without \*args"):

        class _Impl(Base):
            def m(self, a: int) -> int:
                return a


def test_extra_required_positional_with_parent_optional_keyword_raises() -> None:
    class Base(StrictABC):
        @abstractmethod
        def m(self, *, a: int = 1) -> int: ...

    with pytest.raises(TypeError, match="new required parameter 'a'"):

        class _Impl(Base):
            def m(self, a: int) -> int:
                return a


def test_fewer_positional_parameters_with_varargs_and_kwargs_allowed() -> None:
    class Base(StrictABC):
        @abstractmethod
        def m(self, a: int, b: int) -> int: ...

    class Impl(Base):
        def m(self, *args: int, **kwargs: int) -> int:
            return sum(args) + sum(kwargs.values())

    assert Impl().m(1, 2) == 3
    assert Impl().m(a=1, b=2) == 3


# ===================================================================
# check_names
# ===================================================================


def test_check_names_enabled_raises() -> None:
    class Base(StrictABC):
        __strict_options__ = {"check_names": True}

        @abstractmethod
        def m(self, alpha: int) -> int: ...

    with pytest.raises(TypeError, match="parameter name mismatch"):

        class _Impl(Base):
            def m(self, beta: int) -> int:
                return beta


def test_check_names_disabled_allows_rename_positional_only() -> None:
    class Base(StrictABC):
        @abstractmethod
        def m(self, alpha: int, /) -> int: ...

    class Impl(Base):
        def m(self, beta: int) -> int:
            return beta

    assert Impl().m(1) == 1


def test_check_names_enabled_raises_for_positional_only() -> None:
    class Base(StrictABC):
        __strict_options__ = {"check_names": True}

        @abstractmethod
        def m(self, alpha: int, /) -> int: ...

    with pytest.raises(TypeError, match="parameter name mismatch"):

        class _Impl(Base):
            def m(self, beta: int) -> int:
                return beta


def test_check_names_rejects_kwonly_rename_absorbed_by_kwargs() -> None:
    class Base(StrictABC):
        __strict_options__ = {"check_names": True}

        @abstractmethod
        def m(self, *, host: str) -> None: ...

    with pytest.raises(TypeError, match="parameter name mismatch"):

        class _Impl(Base):
            def m(self, *, address: str = "", **kwargs: object) -> None: ...


# ===================================================================
# Positional-or-keyword rename / keyword contract
# ===================================================================


def test_positional_or_keyword_rename_raises_by_default() -> None:
    class Base(StrictABC):
        @abstractmethod
        def m(self, a: int) -> int: ...

    with pytest.raises(TypeError, match="cannot accept parent keyword parameter"):

        class _Impl(Base):
            def m(self, b: int) -> int:
                return b


def test_positional_or_keyword_rename_with_kwargs_and_default_allowed() -> None:
    class Base(StrictABC):
        @abstractmethod
        def m(self, a: int) -> int: ...

    class Impl(Base):
        def m(self, b: int = 0, **kwargs: int) -> int:
            return int(kwargs.get("a", b))

    assert Impl().m(1) == 1
    assert Impl().m(a=2) == 2


def test_positional_or_keyword_rename_with_kwargs_required_raises() -> None:
    """Renaming a positional-or-keyword param with **kwargs but no default
    is unsafe: ``obj.m(a=2)`` leaves the required child param unfilled."""

    class Base(StrictABC):
        @abstractmethod
        def m(self, a: int) -> int: ...

    with pytest.raises(TypeError, match="has no default"):

        class _Impl(Base):
            def m(self, b: int, **kwargs: int) -> int:
                return b


def test_reordered_optional_parameters_allowed() -> None:
    class Base(StrictABC):
        @abstractmethod
        def m(self, a: int = 0) -> int: ...

    class Impl(Base):
        def m(self, b: int = 1, a: int = 0) -> int:
            return a + b

    assert Impl().m() == 1
    assert Impl().m(5) == 5
    assert Impl().m(a=5) == 6


def test_parent_keyword_absorbed_by_other_positional_only_and_kwargs_allowed() -> None:
    class Base(StrictABC):
        @abstractmethod
        def m(self, a: int) -> int: ...

    class Impl(Base):
        def m(self, b: int = 1, /, **kwargs: int) -> int:
            return b + sum(kwargs.values())

    assert Impl().m(5) == 5
    assert Impl().m(a=5) == 6


def test_same_positional_only_required_parameter_with_kwargs_raises() -> None:
    class Base(StrictABC):
        @abstractmethod
        def m(self, a: int) -> None: ...

    with pytest.raises(TypeError, match="kind transition"):

        class _Impl(Base):
            def m(self, a: int, /, **kwargs: int) -> None: ...


def test_reordered_parent_positional_only_does_not_create_keyword_collision() -> None:
    class Base(StrictABC):
        @abstractmethod
        def m(self, a: int, b: int, /) -> None: ...

    class Impl(Base):
        def m(self, b: int, a: int) -> None: ...

    Impl().m(1, 2)


def test_parent_keyword_colliding_with_reordered_child_parameter_raises() -> None:
    class Base(StrictABC):
        @abstractmethod
        def m(self, key: str, /, *, value: int) -> None: ...

    with pytest.raises(TypeError, match="multiple values"):

        class _Impl(Base):
            def m(self, value: int) -> None: ...


def test_swapped_positional_parameters_collision_raises() -> None:
    class Base(StrictABC):
        @abstractmethod
        def m(self, a: int, b: int = 1) -> None: ...

    with pytest.raises(TypeError, match="multiple values"):

        class _Impl(Base):
            def m(self, b: int = 1, a: int = 0) -> None: ...


def test_parent_varargs_keyword_only_collision_with_child_positional_raises() -> None:
    class Base(StrictABC):
        @abstractmethod
        def m(self, *args: int, b: int = 1) -> None: ...

    with pytest.raises(TypeError, match="multiple values"):

        class _Impl(Base):
            def m(self, b: int = 1, *args: int) -> None: ...


def test_reordered_required_child_parameter_without_default_raises() -> None:
    class Base(StrictABC):
        @abstractmethod
        def m(self, a: int) -> None: ...

    with pytest.raises(TypeError, match="has no default"):

        class _Impl(Base):
            def m(self, b: int, a: int = 0) -> None: ...


def test_keyword_only_rename_raises_by_default() -> None:
    class Base(StrictABC):
        @abstractmethod
        def m(self, *, a: int) -> int: ...

    with pytest.raises(TypeError, match="cannot accept parent keyword parameter"):

        class _Impl(Base):
            def m(self, *, b: int) -> int:
                return b


def test_keyword_only_reorder_allowed() -> None:
    class Base(StrictABC):
        @abstractmethod
        def m(self, *, a: int, b: int = 1) -> int: ...

    class Impl(Base):
        def m(self, *, b: int = 1, a: int) -> int:
            return a + b

    assert Impl().m(a=1) == 2
    assert Impl().m(a=1, b=2) == 3


def test_keyword_only_required_as_positional_or_keyword_required_allowed() -> None:
    class Base(StrictABC):
        @abstractmethod
        def m(self, *, a: int) -> int: ...

    class Impl(Base):
        def m(self, a: int) -> int:
            return a

    assert Impl().m(a=1) == 1


def test_keyword_only_required_as_positional_only_required_raises() -> None:
    class Base(StrictABC):
        @abstractmethod
        def m(self, *, a: int) -> int: ...

    with pytest.raises(TypeError, match="new required parameter 'a'"):

        class _Impl(Base):
            def m(self, a: int, /) -> int:
                return a


def test_optional_positional_before_keyword_only_allowed() -> None:
    class Base(StrictABC):
        @abstractmethod
        def m(self, *, a: int) -> int: ...

    class Impl(Base):
        def m(self, x: int = 0, *args: int, a: int) -> int:
            return a + x + sum(args)

    assert Impl().m(a=1) == 1
    assert Impl().m(10, 20, a=1) == 31


# ===================================================================
# Positional-or-keyword → keyword-only transition
# ===================================================================


def test_positional_or_keyword_to_keyword_only_without_varargs_raises() -> None:
    class Base(StrictABC):
        @abstractmethod
        def m(self, a: int) -> int: ...

    with pytest.raises(TypeError, match=r"without \*args"):

        class _Impl(Base):
            def m(self, *, a: int) -> int:
                return a


def test_positional_or_keyword_to_keyword_only_with_varargs_required_raises() -> None:
    class Base(StrictABC):
        @abstractmethod
        def m(self, a: int) -> int: ...

    with pytest.raises(TypeError, match="must have a default value"):

        class _Impl(Base):
            def m(self, *args: int, a: int) -> int:
                return a


def test_positional_or_keyword_to_keyword_only_with_varargs_default_allowed() -> None:
    class Base(StrictABC):
        @abstractmethod
        def m(self, a: int) -> int: ...

    class Impl(Base):
        def m(self, *args: int, a: int = 1) -> int:
            return a + sum(args)

    assert Impl().m(1) == 2
    assert Impl().m(a=2) == 2


# ===================================================================
# Variadic parameters
# ===================================================================


def test_parent_var_positional_child_fixed_raises() -> None:
    class Base(StrictABC):
        @abstractmethod
        def m(self, *args: int) -> None: ...

    with pytest.raises(TypeError, match=r"removed \*args"):

        class _Impl(Base):
            def m(self) -> None: ...


def test_parent_var_keyword_child_fixed_raises() -> None:
    class Base(StrictABC):
        @abstractmethod
        def m(self, **kwargs: int) -> None: ...

    with pytest.raises(TypeError, match=r"removed \*\*kwargs"):

        class _Impl(Base):
            def m(self) -> None: ...


def test_parent_both_child_missing_kwargs_raises() -> None:
    class Base(StrictABC):
        @abstractmethod
        def m(self, *args: int, **kwargs: int) -> None: ...

    with pytest.raises(TypeError, match=r"removed \*\*kwargs"):

        class _Impl(Base):
            def m(self, *args: int) -> None: ...


def test_parent_fixed_child_adds_varargs_allowed() -> None:
    class Base(StrictABC):
        @abstractmethod
        def m(self, a: int) -> int: ...

    class Impl(Base):
        def m(self, a: int, *args: int) -> int:
            return a + sum(args)

    assert Impl().m(1, 2, 3) == 6


def test_parent_fixed_child_adds_kwargs_allowed() -> None:
    class Base(StrictABC):
        @abstractmethod
        def m(self, a: int) -> int: ...

    class Impl(Base):
        def m(self, a: int, **kwargs: int) -> int:
            return a + sum(kwargs.values())

    assert Impl().m(1, b=2) == 3


def test_parent_varargs_child_varargs_kwargs_allowed() -> None:
    class Base(StrictABC):
        @abstractmethod
        def m(self, *args: int) -> None: ...

    class Impl(Base):
        def m(self, *args: int, **kwargs: int) -> None: ...

    Impl().m(1, x=2)


def test_parent_varargs_child_required_extra_raises() -> None:
    class Base(StrictABC):
        @abstractmethod
        def m(self, *args: int) -> None: ...

    with pytest.raises(TypeError, match="new required parameter 'a'"):

        class _Impl(Base):
            def m(self, a: int, *args: int) -> None: ...


def test_parent_varargs_child_optional_extra_allowed() -> None:
    class Base(StrictABC):
        @abstractmethod
        def m(self, *args: int) -> int: ...

    class Impl(Base):
        def m(self, a: int = 1, *args: int) -> int:
            return a + sum(args)

    assert Impl().m() == 1
    assert Impl().m(5) == 5


def test_parent_varargs_child_removes_default_on_existing_raises() -> None:
    class Base(StrictABC):
        @abstractmethod
        def m(self, a: int = 1, *args: int) -> int: ...

    with pytest.raises(TypeError, match="removing default value"):

        class _Impl(Base):
            def m(self, a: int, *args: int) -> int:
                return a


# ===================================================================
# Keyword absorption
# ===================================================================


def test_parent_keyword_only_missing_without_kwargs_raises() -> None:
    class Base(StrictABC):
        @abstractmethod
        def m(self, a: int, *, b: int = 1) -> int: ...

    with pytest.raises(TypeError, match="cannot accept parent keyword parameter 'b'"):

        class _Impl(Base):
            def m(self, a: int, *args: int) -> int:
                return a


def test_parent_keyword_only_absorbed_by_kwargs_allowed() -> None:
    class Base(StrictABC):
        @abstractmethod
        def m(self, a: int, *, b: int = 1) -> int: ...

    class Impl(Base):
        def m(self, a: int, *args: int, **kwargs: int) -> int:
            return a + int(kwargs.get("b", 0))

    assert Impl().m(1, b=2) == 3


def test_missing_positional_or_keyword_keyword_requires_kwargs() -> None:
    class Base(StrictABC):
        @abstractmethod
        def m(self, a: int, *args: int) -> int: ...

    with pytest.raises(TypeError, match=r"without \*\*kwargs"):

        class _Impl(Base):
            def m(self, *args: int) -> int:
                return sum(args)


def test_missing_positional_or_keyword_absorbed_by_both_variadics_allowed() -> None:
    class Base(StrictABC):
        @abstractmethod
        def m(self, a: int, *args: int) -> int: ...

    class Impl(Base):
        def m(self, *args: int, **kwargs: int) -> int:
            return int(kwargs.get("a", 0)) + sum(args)

    assert Impl().m(a=5) == 5


def test_missing_positional_only_absorbed_by_varargs_allowed() -> None:
    class Base(StrictABC):
        @abstractmethod
        def m(self, a: int, /, *args: int) -> int: ...

    class Impl(Base):
        def m(self, *args: int) -> int:
            return sum(args)

    assert Impl().m(1, 2) == 3


def test_extra_required_keyword_only_raises() -> None:
    class Base(StrictABC):
        @abstractmethod
        def m(self, a: int, **kwargs: int) -> int: ...

    with pytest.raises(TypeError, match="new required keyword-only parameter 'b'"):

        class _Impl(Base):
            def m(self, a: int, *, b: int, **kwargs: int) -> int:
                return a + b


def test_extra_optional_keyword_only_allowed() -> None:
    class Base(StrictABC):
        @abstractmethod
        def m(self, a: int, **kwargs: int) -> int: ...

    class Impl(Base):
        def m(self, a: int, *, b: int = 1, **kwargs: int) -> int:
            return a + b + sum(kwargs.values())

    assert Impl().m(1) == 2


# ===================================================================
# Parameter kind transitions
# ===================================================================


def test_positional_only_to_positional_or_keyword_allowed() -> None:
    class Base(StrictABC):
        @abstractmethod
        def m(self, a: int, /) -> int: ...

    class Impl(Base):
        def m(self, a: int) -> int:
            return a

    assert Impl().m(1) == 1


def test_positional_or_keyword_to_positional_only_raises() -> None:
    class Base(StrictABC):
        @abstractmethod
        def m(self, a: int) -> int: ...

    with pytest.raises(TypeError, match="kind transition"):

        class _Impl(Base):
            def m(self, a: int, /) -> int:
                return a


def test_keyword_only_to_positional_or_keyword_allowed() -> None:
    class Base(StrictABC):
        @abstractmethod
        def m(self, *, a: int) -> int: ...

    class Impl(Base):
        def m(self, a: int) -> int:
            return a

    assert Impl().m(a=1) == 1


# ===================================================================
# _validate_signature: direct tests
# ===================================================================


def test_validate_signature_appends_violations() -> None:
    """``_validate_signature`` collects violations into a list instead of
    raising immediately."""

    def parent(self: Any, a: int = 1) -> None: ...
    def child(self: Any, a: int) -> None: ...

    sig_p = inspect.signature(parent)
    sig_c = inspect.signature(child)
    violations: list[LSPViolation] = []

    StrictABCMeta._validate_signature(
        meth_name="m",
        sig_parent=sig_p,
        sig_child=sig_c,
        parent_descriptor="instancemethod",
        child_descriptor="instancemethod",
        check_names=False,
        check_defaults=True,
        check_types=False,
        check_types_contravariant=False,
        check_return_type=False,
        class_name="C",
        violations=violations,
    )

    assert len(violations) == 1
    assert "removing default value" in violations[0].reason


def test_validate_signature_handles_empty_params_for_non_static() -> None:
    sig = inspect.signature(lambda: None)
    violations: list[LSPViolation] = []

    StrictABCMeta._validate_signature(
        meth_name="m",
        sig_parent=sig,
        sig_child=sig,
        parent_descriptor="instancemethod",
        child_descriptor="instancemethod",
        check_names=False,
        check_defaults=True,
        check_types=False,
        check_types_contravariant=False,
        check_return_type=False,
        class_name="C",
        violations=violations,
    )

    assert violations == []
