"""Tests for strict_abc.

Covers signature validation, descriptor checks, option merging,
new features (lsp_exempt, strict decorator, warn mode, contravariant
types, async mismatch), and defensive / edge-case branches.
"""


import abc
import asyncio
import functools
import inspect
import typing
import warnings
from abc import ABC, abstractmethod
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

import strict_abc
from strict_abc import (
    LSPViolation,
    StrictABC,
    StrictABCMeta,
    __version__,
    lsp_exempt,
    strict,
)

# ===================================================================
# Package-level
# ===================================================================


def test_version_is_string() -> None:
    assert isinstance(__version__, str)


def test_exports() -> None:
    assert set(strict_abc.__all__) == {
        "DescriptorKind",
        "LSPViolation",
        "StrictABC",
        "StrictABCMeta",
        "StrictOptions",
        "__version__",
        "lsp_exempt",
        "strict",
    }


def test_py_typed_exists() -> None:
    assert strict_abc.__file__ is not None
    package_dir = Path(strict_abc.__file__).parent
    assert (package_dir / "py.typed").exists()


# ===================================================================
# LSPViolation exception
# ===================================================================


def test_lsp_violation_is_type_error() -> None:
    exc = LSPViolation("Cls", "meth", "reason")
    assert isinstance(exc, TypeError)


def test_lsp_violation_attributes() -> None:
    exc = LSPViolation("MyClass", "do_thing", "bad signature")
    assert exc.cls_name == "MyClass"
    assert exc.meth_name == "do_thing"
    assert exc.reason == "bad signature"
    assert str(exc) == "MyClass.do_thing: bad signature"


def test_lsp_violation_caught_as_type_error() -> None:
    class Base(StrictABC):
        @abstractmethod
        def m(self, a: int = 1) -> None: ...

    with pytest.raises(TypeError):
        class _Impl(Base):
            def m(self, a: int) -> None: ...


# ===================================================================
# Basic instantiation
# ===================================================================


def test_strict_abc_without_abstract_methods_can_be_instantiated() -> None:
    class Concrete(StrictABC):
        pass

    Concrete()


def test_abstract_class_cannot_be_instantiated() -> None:
    class Base(StrictABC):
        @abstractmethod
        def m(self) -> None: ...

    with pytest.raises(TypeError):
        Base()


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
# check_types
# ===================================================================


def test_check_types_enabled_missing_annotation_raises() -> None:
    class Base(StrictABC):
        __strict_options__ = {"check_types": True}

        @abstractmethod
        def m(self, a: int) -> int: ...

    with pytest.raises(TypeError, match="missing type annotation"):
        class _Impl(Base):
            def m(self, a):
                return a


def test_check_types_enabled_mismatch_raises() -> None:
    class Base(StrictABC):
        __strict_options__ = {"check_types": True}

        @abstractmethod
        def m(self, a: int) -> int: ...

    with pytest.raises(TypeError, match="type annotation mismatch"):
        class _Impl(Base):
            def m(self, a: str) -> int:
                return "x"


def test_check_types_enabled_exact_allowed() -> None:
    class Base(StrictABC):
        __strict_options__ = {"check_types": True}

        @abstractmethod
        def m(self, a: int) -> int: ...

    class Impl(Base):
        def m(self, a: int) -> int:
            return a

    assert Impl().m(1) == 1


def test_check_types_disabled_allows_mismatch() -> None:
    class Base(StrictABC):
        @abstractmethod
        def m(self, a: int) -> int: ...

    class Impl(Base):
        def m(self, a: str) -> int:
            return "x"

    assert Impl().m("1") == "x"


def test_check_types_keyword_only_mismatch_raises() -> None:
    class Base(StrictABC):
        __strict_options__ = {"check_types": True}

        @abstractmethod
        def m(self, *, a: int) -> int: ...

    with pytest.raises(TypeError, match="type annotation mismatch"):
        class _Impl(Base):
            def m(self, *, a: str) -> int:
                return "x"


def test_check_types_keyword_only_missing_annotation_raises() -> None:
    class Base(StrictABC):
        __strict_options__ = {"check_types": True}

        @abstractmethod
        def m(self, *, a: int) -> int: ...

    with pytest.raises(TypeError, match="missing type annotation"):
        class _Impl(Base):
            def m(self, *, a):
                return a


def test_check_types_allows_missing_parent_annotation_positional() -> None:
    class Base(StrictABC):
        __strict_options__ = {"check_types": True}

        @abstractmethod
        def m(self, a): ...

    class Impl(Base):
        def m(self, a: int) -> int:
            return a

    assert Impl().m(1) == 1


def test_check_types_allows_missing_parent_annotation_keyword_only() -> None:
    class Base(StrictABC):
        __strict_options__ = {"check_types": True}

        @abstractmethod
        def m(self, *, a): ...

    class Impl(Base):
        def m(self, *, a: int) -> int:
            return a

    assert Impl().m(a=1) == 1


def test_check_types_allows_no_annotations() -> None:
    class Base(StrictABC):
        __strict_options__ = {"check_types": True}

        @abstractmethod
        def m(self, a): ...

    class Impl(Base):
        def m(self, a):
            return a

    assert Impl().m(1) == 1


def test_check_types_normalizes_none_annotation() -> None:
    class Base(StrictABC):
        __strict_options__ = {"check_types": True}

        @abstractmethod
        def m(self, a: None) -> None: ...

    class Impl(Base):
        def m(self, a: None) -> None:
            return None

    Impl().m(None)


# ===================================================================
# check_types_contravariant
# ===================================================================


def test_contravariant_wider_type_allowed() -> None:
    class Base(StrictABC):
        __strict_options__ = {"check_types_contravariant": True}

        @abstractmethod
        def m(self, a: int) -> None: ...

    class Impl(Base):
        def m(self, a: object) -> None: ...

    Impl().m(1)


def test_contravariant_narrower_type_raises() -> None:
    class Base(StrictABC):
        __strict_options__ = {"check_types_contravariant": True}

        @abstractmethod
        def m(self, a: object) -> None: ...

    with pytest.raises(TypeError, match="not contravariant"):
        class _Impl(Base):
            def m(self, a: int) -> None: ...


def test_contravariant_exact_type_allowed() -> None:
    class Base(StrictABC):
        __strict_options__ = {"check_types_contravariant": True}

        @abstractmethod
        def m(self, a: int) -> None: ...

    class Impl(Base):
        def m(self, a: int) -> None: ...

    Impl().m(1)


def test_contravariant_union_widening_allowed() -> None:
    class Base(StrictABC):
        __strict_options__ = {"check_types_contravariant": True}

        @abstractmethod
        def m(self, a: int) -> None: ...

    class Impl(Base):
        def m(self, a: int | str) -> None: ...

    Impl().m(1)
    Impl().m("x")


def test_contravariant_keyword_only() -> None:
    class Base(StrictABC):
        __strict_options__ = {"check_types_contravariant": True}

        @abstractmethod
        def m(self, *, a: int) -> None: ...

    class Impl(Base):
        def m(self, *, a: object) -> None: ...

    Impl().m(a=1)


def test_contravariant_missing_child_annotation_raises() -> None:
    class Base(StrictABC):
        __strict_options__ = {"check_types_contravariant": True}

        @abstractmethod
        def m(self, a: int) -> None: ...

    with pytest.raises(TypeError, match="missing type annotation"):
        class _Impl(Base):
            def m(self, a) -> None: ...


# ===================================================================
# check_return_type
# ===================================================================


def test_return_type_covariance_allowed() -> None:
    class Base(StrictABC):
        __strict_options__ = {"check_return_type": True}

        @abstractmethod
        def m(self) -> object: ...

    class Impl(Base):
        def m(self) -> str:
            return "ok"

    assert Impl().m() == "ok"


def test_return_type_bool_int_allowed() -> None:
    class Base(StrictABC):
        __strict_options__ = {"check_return_type": True}

        @abstractmethod
        def m(self) -> int: ...

    class Impl(Base):
        def m(self) -> bool:
            return True

    assert Impl().m() is True


def test_return_type_not_covariant_raises() -> None:
    class Base(StrictABC):
        __strict_options__ = {"check_return_type": True}

        @abstractmethod
        def m(self) -> str: ...

    with pytest.raises(TypeError, match="return type not covariant"):
        class _Impl(Base):
            def m(self) -> object:
                return object()


def test_return_type_missing_annotation_raises() -> None:
    class Base(StrictABC):
        __strict_options__ = {"check_return_type": True}

        @abstractmethod
        def m(self) -> int: ...

    with pytest.raises(TypeError, match="missing return type annotation"):
        class _Impl(Base):
            def m(self):
                return 1


def test_return_type_disabled_allows_any() -> None:
    class Base(StrictABC):
        @abstractmethod
        def m(self) -> int: ...

    class Impl(Base):
        def m(self) -> str:
            return "x"

    assert Impl().m() == "x"


def test_return_type_none_covariant_allowed() -> None:
    class Base(StrictABC):
        __strict_options__ = {"check_return_type": True}

        @abstractmethod
        def m(self) -> object: ...

    class Impl(Base):
        def m(self) -> None:
            return None

    assert Impl().m() is None


def test_return_type_any_allowed() -> None:
    class Base1(StrictABC):
        __strict_options__ = {"check_return_type": True}

        @abstractmethod
        def m(self) -> Any: ...

    class Impl1(Base1):
        def m(self) -> str:
            return "ok"

    assert Impl1().m() == "ok"

    class Base2(StrictABC):
        __strict_options__ = {"check_return_type": True}

        @abstractmethod
        def m(self) -> str: ...

    class Impl2(Base2):
        def m(self) -> Any:
            return "ok"

    assert Impl2().m() == "ok"


def test_return_type_parent_empty_is_compatible() -> None:
    class Base(StrictABC):
        __strict_options__ = {"check_return_type": True}

        @abstractmethod
        def m(self): ...

    class Impl(Base):
        def m(self) -> int:
            return 1

    class Impl2(Base):
        def m(self):
            return 2

    assert Impl().m() == 1
    assert Impl2().m() == 2


def test_return_type_none_parent_and_child_allowed() -> None:
    class Base(StrictABC):
        __strict_options__ = {"check_return_type": True}

        @abstractmethod
        def m(self) -> None: ...

    class Impl(Base):
        def m(self) -> None:
            return None

    Impl().m()


def test_return_type_generic_exact_allowed() -> None:
    class Base(StrictABC):
        __strict_options__ = {"check_return_type": True}

        @abstractmethod
        def m(self) -> list[int]: ...

    class Impl(Base):
        def m(self) -> list[int]:
            return [1]

    assert Impl().m() == [1]


def test_return_type_generic_args_mismatch_raises() -> None:
    class Base(StrictABC):
        __strict_options__ = {"check_return_type": True}

        @abstractmethod
        def m(self) -> list[object]: ...

    with pytest.raises(TypeError, match="return type not covariant"):
        class _Impl(Base):
            def m(self) -> list[str]:
                return ["x"]


def test_return_type_generic_subclass_allowed_through_class() -> None:
    T = typing.TypeVar("T")

    class MyList(list, typing.Generic[T]):
        pass

    class Base(StrictABC):
        __strict_options__ = {"check_return_type": True}

        @abstractmethod
        def m(self) -> list[int]: ...

    class Impl(Base):
        def m(self) -> MyList[int]:
            return MyList()

    assert Impl().m() == []


# ===================================================================
# Descriptor compatibility
# ===================================================================


def test_staticmethod_valid() -> None:
    class Base(StrictABC):
        @staticmethod
        @abstractmethod
        def m(x: int) -> int: ...

    class Impl(Base):
        @staticmethod
        def m(x: int) -> int:
            return x

    assert Impl.m(2) == 2


def test_staticmethod_descriptor_mismatch_raises() -> None:
    class Base(StrictABC):
        @staticmethod
        @abstractmethod
        def m(x: int) -> int: ...

    with pytest.raises(TypeError, match="descriptor type mismatch"):
        class _Impl(Base):
            def m(self, x: int) -> int:
                return x


def test_classmethod_valid() -> None:
    class Base(StrictABC):
        @classmethod
        @abstractmethod
        def m(cls, x: int) -> int: ...

    class Impl(Base):
        @classmethod
        def m(cls, x: int) -> int:
            return x

    assert Impl.m(3) == 3


def test_classmethod_descriptor_mismatch_raises() -> None:
    class Base(StrictABC):
        @classmethod
        @abstractmethod
        def m(cls, x: int) -> int: ...

    with pytest.raises(TypeError, match="descriptor type mismatch"):
        class _Impl(Base):
            @staticmethod
            def m(x: int) -> int:
                return x


def test_abstract_property_to_property_allowed() -> None:
    class Base(StrictABC):
        @property
        @abstractmethod
        def value(self) -> int: ...

    class Impl(Base):
        @property
        def value(self) -> int:
            return 1

    assert Impl().value == 1


def test_method_to_property_descriptor_mismatch_raises() -> None:
    class Base(StrictABC):
        @abstractmethod
        def m(self) -> int: ...

    with pytest.raises(TypeError, match="descriptor type mismatch"):
        class _Impl(Base):
            @property
            def m(self) -> int:
                return 1


def test_property_to_method_descriptor_mismatch_raises() -> None:
    class Base(StrictABC):
        @property
        @abstractmethod
        def value(self) -> int: ...

    with pytest.raises(TypeError, match="descriptor type mismatch"):
        class _Impl(Base):
            def value(self) -> int:
                return 1


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


# ===================================================================
# Metaclass direct usage / abstract chain
# ===================================================================


def test_can_use_metaclass_directly() -> None:
    class Base(metaclass=StrictABCMeta):
        @abstractmethod
        def m(self) -> int: ...

    with pytest.raises(TypeError):
        Base()

    class Impl(Base):
        def m(self) -> int:
            return 1

    assert Impl().m() == 1


def test_subclass_can_keep_method_abstract() -> None:
    class Base(StrictABC):
        @abstractmethod
        def m(self) -> None: ...

    class Middle(Base):
        @abstractmethod
        def m(self) -> None: ...

    with pytest.raises(TypeError):
        Middle()


def test_non_abstract_methods_are_not_validated() -> None:
    class Base(StrictABC):
        def m(self, a: int) -> int:
            return a

    class Impl(Base):
        def m(self, a: int, b: int = 0) -> int:
            return a + b

    assert Impl().m(1) == 1
    assert Impl().m(1, 2) == 3


# ===================================================================
# Mixins / multiple inheritance
# ===================================================================


def test_mixin_inherited_implementation_is_validated() -> None:
    class Base(StrictABC):
        @abstractmethod
        def m(self, a: int = 1) -> None: ...

    class Mixin:
        def m(self, a: int) -> None: ...

    with pytest.raises(TypeError, match="removing default value"):
        class _Impl(Mixin, Base):
            pass


def test_mixin_after_abstract_base_keeps_class_abstract() -> None:
    class Base(StrictABC):
        @abstractmethod
        def m(self, a: int = 1) -> None: ...

    class Mixin:
        def m(self, a: int) -> None: ...

    class Abstract(Base, Mixin):
        pass

    with pytest.raises(TypeError):
        Abstract()


def test_multiple_abstract_bases_are_validated() -> None:
    class A(StrictABC):
        @abstractmethod
        def m(self, a: int) -> None: ...

    class B(StrictABC):
        @abstractmethod
        def m(self, a: int, b: int) -> None: ...

    with pytest.raises(TypeError, match=r"without \*args"):
        class _C(A, B):
            def m(self, a: int) -> None: ...


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
# Defensive / edge-case branches
# ===================================================================


def test_parent_abstractmethods_not_frozenset_or_set_is_ignored() -> None:
    class FakeBase:
        __abstractmethods__ = ["m"]  # type: ignore[assignment]

    class C(FakeBase, metaclass=StrictABCMeta):
        pass

    C()


def test_parent_abstractmethods_set_is_accepted() -> None:
    """A plain ``set`` for ``__abstractmethods__`` is processed, but since
    there is no real abstract attribute, no validation occurs."""

    class FakeBase:
        __abstractmethods__ = {"m"}  # type: ignore[assignment]

    class C(FakeBase, metaclass=StrictABCMeta):
        pass

    C()


def test_parent_abstractmethods_frozenset_without_concrete_is_skipped() -> None:
    class FakeBase:
        __abstractmethods__ = frozenset({"m"})

    class C(FakeBase, metaclass=StrictABCMeta):
        pass

    C()


def test_parent_abstractmethods_frozenset_with_concrete_but_no_abstract_attr() -> None:
    class FakeBase:
        __abstractmethods__ = frozenset({"m"})

    class C(FakeBase, metaclass=StrictABCMeta):
        def m(self) -> int:
            return 1

    assert C().m() == 1


def test_cls_abstracts_non_frozenset_branch(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_new(
        mcls: type,
        name: str,
        bases: tuple[type, ...],
        namespace: dict[str, Any],
        **kwargs: Any,
    ) -> type:
        dummy = type("Dummy", (), {})
        dummy.__abstractmethods__ = ["not-a-frozenset"]  # type: ignore[assignment]
        return dummy

    monkeypatch.setattr(abc.ABCMeta, "__new__", fake_new)

    cls = StrictABCMeta.__new__(StrictABCMeta, "C", (), {})
    assert cls.__abstractmethods__ == ["not-a-frozenset"]


def test_concrete_attr_reported_abstract_is_skipped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Base(StrictABC):
        @abstractmethod
        def m(self) -> int: ...

    abstract_attr = Base.__dict__["m"]

    monkeypatch.setattr(
        StrictABCMeta,
        "_find_concrete_attr",
        staticmethod(lambda cls, name: abstract_attr),
    )

    class Impl(Base):
        def m(self, x: int) -> int:
            return x

    assert Impl().m(3) == 3


# ===================================================================
# Descriptor kind / unwrap defensive branches
# ===================================================================


def test_descriptor_kind_typeerror_on_parent_attr_is_skipped() -> None:
    class NonCallableDescriptor:
        __isabstractmethod__ = True

        def __get__(self, obj: Any, objtype: Any = None) -> Any:
            return self

    class Base(StrictABC):
        m = NonCallableDescriptor()

    class Impl(Base):
        m = 1  # type: ignore[assignment]

    Impl()


def test_descriptor_kind_typeerror_on_child_attr_is_skipped() -> None:
    class Base(StrictABC):
        @abstractmethod
        def m(self) -> int: ...

    class Impl(Base):
        m = 1  # type: ignore[assignment]

    Impl()


def test_property_without_getter_is_skipped() -> None:
    class AbstractProperty(property):
        __isabstractmethod__ = True

        def __init__(self) -> None:
            super().__init__(fget=None)

    class Base(StrictABC):
        m = AbstractProperty()

    class Impl(Base):
        @property
        def m(self) -> int:
            return 1

    assert Impl().m == 1


def test_descriptor_kind_all_supported_and_unsupported() -> None:
    def f(self: Any) -> None:
        return None

    prop = property(lambda self: 1)
    sm = staticmethod(lambda: 1)
    cm = classmethod(lambda cls: 1)

    assert StrictABCMeta._descriptor_kind(prop) == "property"
    assert StrictABCMeta._descriptor_kind(sm) == "staticmethod"
    assert StrictABCMeta._descriptor_kind(cm) == "classmethod"
    assert StrictABCMeta._descriptor_kind(f) == "instancemethod"

    with pytest.raises(TypeError, match="Unsupported descriptor type"):
        StrictABCMeta._descriptor_kind(1)


def test_unwrap_descriptor_all_supported_and_unsupported() -> None:
    def f(self: Any) -> None:
        return None

    prop = property(f)
    sm = staticmethod(f)
    cm = classmethod(f)

    func, kind = StrictABCMeta._unwrap_descriptor(prop)
    assert func is f
    assert kind == "property"

    func, kind = StrictABCMeta._unwrap_descriptor(sm)
    assert func is sm.__func__
    assert kind == "staticmethod"

    func, kind = StrictABCMeta._unwrap_descriptor(cm)
    assert func is cm.__func__
    assert kind == "classmethod"

    func, kind = StrictABCMeta._unwrap_descriptor(f)
    assert func is f
    assert kind == "instancemethod"

    with pytest.raises(TypeError, match="Property without getter cannot be inspected"):
        StrictABCMeta._unwrap_descriptor(property(None))

    with pytest.raises(TypeError, match="Unsupported descriptor type"):
        StrictABCMeta._unwrap_descriptor(1)


def test_unwrap_descriptor_final_defensive_raise(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        StrictABCMeta,
        "_descriptor_kind",
        lambda attr: "instancemethod",
    )

    with pytest.raises(TypeError, match="Unsupported descriptor type"):
        StrictABCMeta._unwrap_descriptor(1)


# ===================================================================
# Signature fallback
# ===================================================================


def test_signature_falls_back_when_eval_str_fails() -> None:
    def f(x: "UndefinedAnnotation") -> "UndefinedAnnotation":  # noqa: F821
        return x

    sig = StrictABCMeta._signature(f)

    assert isinstance(sig, inspect.Signature)
    assert sig.parameters["x"].annotation == "UndefinedAnnotation"


def test_signature_name_error_is_swallowed_during_class_creation() -> None:
    class NameErrorSignature:
        __isabstractmethod__ = True

        def __call__(self) -> None:
            return None

        @property
        def __signature__(self) -> Any:
            raise NameError("boom")

    class ConcreteNameErrorSignature(NameErrorSignature):
        __isabstractmethod__ = False

    class Base(StrictABC):
        m = NameErrorSignature()

    class Impl(Base):
        m = ConcreteNameErrorSignature()

    Impl()


def test_signature_value_error_is_swallowed_during_class_creation() -> None:
    class ValueErrorSignature:
        __isabstractmethod__ = True

        def __call__(self) -> None:
            return None

        @property
        def __signature__(self) -> Any:
            raise ValueError("boom")

    class ConcreteValueErrorSignature(ValueErrorSignature):
        __isabstractmethod__ = False

    class Base(StrictABC):
        m = ValueErrorSignature()

    class Impl(Base):
        m = ConcreteValueErrorSignature()

    Impl()


def test_signature_unwraps_decorated_functions() -> None:
    """``inspect.unwrap`` is applied so ``@functools.wraps`` decorators
    do not hide the real signature."""

    def decorator(fn: Any) -> Any:
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            return fn(*args, **kwargs)

        return wrapper

    class Base(StrictABC):
        @abstractmethod
        def m(self, a: int = 1) -> int: ...

    class Impl(Base):
        @decorator
        def m(self, a: int = 1) -> int:
            return a

    assert Impl().m() == 1
    assert Impl().m(5) == 5


# ===================================================================
# _is_return_compatible: rare and defensive branches
# ===================================================================


def test_is_return_compatible_parent_empty() -> None:
    assert StrictABCMeta._is_return_compatible(inspect.Signature.empty, int) is True


def test_is_return_compatible_child_empty() -> None:
    assert StrictABCMeta._is_return_compatible(int, inspect.Signature.empty) is False


def test_is_return_compatible_none() -> None:
    assert StrictABCMeta._is_return_compatible(None, None) is True


def test_is_return_compatible_issubclass_typeerror() -> None:
    class EvilMeta(type):
        def __subclasscheck__(cls, subclass: Any) -> bool:
            raise TypeError

    class Evil(metaclass=EvilMeta):
        pass

    assert StrictABCMeta._is_return_compatible(Evil, int) is False


def test_is_return_compatible_generic_subclass_origin() -> None:
    T = typing.TypeVar("T")

    class MyList(list, typing.Generic[T]):
        pass

    assert StrictABCMeta._is_return_compatible(list[int], MyList[int]) is True


def test_is_return_compatible_generic_origin_not_subclass() -> None:
    assert StrictABCMeta._is_return_compatible(list[int], dict[str, int]) is False


def test_is_return_compatible_generic_origin_not_type() -> None:
    assert (
        StrictABCMeta._is_return_compatible(
            int | str,
            int | bytes,
        )
        is False
    )


def test_is_return_compatible_generic_one_origin_missing() -> None:
    assert StrictABCMeta._is_return_compatible(list[int], list) is False
    assert StrictABCMeta._is_return_compatible(list, list[int]) is False


def test_is_return_compatible_generic_issubclass_typeerror() -> None:
    class EvilMeta(type):
        def __subclasscheck__(cls, subclass: Any) -> bool:
            raise TypeError

    class EvilOrigin(metaclass=EvilMeta):
        pass

    class FakeGeneric:
        def __init__(self, origin: Any, args: tuple[Any, ...]) -> None:
            self.__origin__ = origin
            self.__args__ = args

        def __eq__(self, other: object) -> bool:
            return False

    p = FakeGeneric(EvilOrigin, (int,))
    c = FakeGeneric(list, (int,))

    assert StrictABCMeta._is_return_compatible(p, c) is False


def test_is_return_compatible_generic_equality_second_check() -> None:
    class ToggleEqGeneric:
        def __init__(self, origin: Any, args: tuple[Any, ...]) -> None:
            self.__origin__ = origin
            self.__args__ = args
            self._first = True

        def __eq__(self, other: object) -> bool:
            if self._first:
                self._first = False
                return False
            return True

    p = ToggleEqGeneric(list, (int,))
    c = ToggleEqGeneric(list, (int,))

    assert StrictABCMeta._is_return_compatible(p, c) is True


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


# ===================================================================
# _find_concrete_attr / _find_abstract_attrs
# ===================================================================


def test_find_concrete_attr_skips_abstract_before_concrete() -> None:
    class Base(StrictABC):
        @abstractmethod
        def m(self) -> int: ...

    class Mixin:
        def m(self) -> int:
            return 1

    class C(Base, Mixin):
        pass

    with pytest.raises(TypeError):
        C()

    attr = StrictABCMeta._find_concrete_attr(C, "m")
    assert attr is Mixin.__dict__["m"]


def test_find_concrete_attr_returns_none_if_only_abstract() -> None:
    class Base(StrictABC):
        @abstractmethod
        def m(self) -> int: ...

    assert StrictABCMeta._find_concrete_attr(Base, "m") is None


def test_find_abstract_attrs_deduplicates_same_object() -> None:
    abstract = abstractmethod(lambda self: None)

    class A(StrictABC):
        m = abstract

    class B(StrictABC):
        m = abstract

    class C(A, B):
        def m(self) -> None:
            return None

    attrs = StrictABCMeta._find_abstract_attrs(C, "m")
    assert len(attrs) == 1


def test_find_abstract_attrs_skips_non_abstract_attrs() -> None:
    class Base(StrictABC):
        @abstractmethod
        def m(self) -> int: ...

    class Mixin:
        def m(self) -> int:
            return 1

    class C(Base, Mixin):
        pass

    attrs = StrictABCMeta._find_abstract_attrs(C, "m")
    assert attrs == [Base.__dict__["m"]]


# ===================================================================
# lsp_exempt decorator
# ===================================================================


def test_lsp_exempt_skips_validation() -> None:
    class Base(StrictABC):
        @abstractmethod
        def m(self, a: int = 1) -> int: ...

    class Impl(Base):
        @lsp_exempt
        def m(self, a: int) -> int:
            return a

    assert Impl().m(5) == 5


def test_lsp_exempt_sets_attribute() -> None:
    def f() -> None: ...

    result = lsp_exempt(f)
    assert result is f
    assert f.__lsp_exempt__ is True  # type: ignore[attr-defined]


def test_lsp_exempt_descriptor_mismatch_skipped() -> None:
    class Base(StrictABC):
        @staticmethod
        @abstractmethod
        def m(x: int) -> int: ...

    class Impl(Base):
        @lsp_exempt
        def m(self, x: int) -> int:  # type: ignore[override]
            return x

    assert Impl().m(1) == 1


# ===================================================================
# strict() class decorator
# ===================================================================


def test_strict_decorator_injects_options() -> None:
    @strict(check_names=True)
    class Base(ABC, metaclass=StrictABCMeta):
        @abstractmethod
        def m(self, alpha: int, /) -> int: ...

    assert Base.__strict_options__ == {"check_names": True}  # type: ignore[attr-defined]

    with pytest.raises(TypeError, match="parameter name mismatch"):
        class _Impl(Base):
            def m(self, beta: int) -> int:
                return beta


def test_strict_decorator_does_not_affect_other_classes() -> None:
    @strict(check_types=True)
    class A(ABC, metaclass=StrictABCMeta):
        @abstractmethod
        def m(self, a: int) -> None: ...

    class B(StrictABC):
        @abstractmethod
        def m(self, a: int) -> None: ...

    # B should still use defaults (check_types=False).
    class ImplB(B):
        def m(self, a: str) -> None: ...

    ImplB().m("x")


# ===================================================================
# mode="warn"
# ===================================================================


def test_warn_mode_emits_warning_instead_of_raising() -> None:
    class Base(StrictABC):
        __strict_options__ = {"mode": "warn"}

        @abstractmethod
        def m(self, a: int = 1) -> int: ...

    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")

        class Impl(Base):
            def m(self, a: int) -> int:
                return a

    lsp_warnings = [x for x in w if issubclass(x.category, UserWarning)]
    assert len(lsp_warnings) == 1
    assert "removing default value" in str(lsp_warnings[0].message)

    assert Impl().m(5) == 5


def test_error_mode_raises_by_default() -> None:
    class Base(StrictABC):
        @abstractmethod
        def m(self, a: int = 1) -> int: ...

    with pytest.raises(LSPViolation):
        class _Impl(Base):
            def m(self, a: int) -> int:
                return a


# ===================================================================
# Async / sync mismatch
# ===================================================================


def test_async_abstract_sync_impl_raises() -> None:
    class Base(StrictABC):
        @abstractmethod
        async def m(self) -> int: ...

    with pytest.raises(TypeError, match="async/sync mismatch"):
        class _Impl(Base):
            def m(self) -> int:
                return 1


def test_sync_abstract_async_impl_raises() -> None:
    class Base(StrictABC):
        @abstractmethod
        def m(self) -> int: ...

    with pytest.raises(TypeError, match="async/sync mismatch"):
        class _Impl(Base):
            async def m(self) -> int:
                return 1


def test_async_abstract_async_impl_allowed() -> None:
    class Base(StrictABC):
        @abstractmethod
        async def m(self, a: int = 1) -> int: ...

    class Impl(Base):
        async def m(self, a: int = 1) -> int:
            return a

    assert asyncio.run(Impl().m()) == 1


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


# ===================================================================
# _is_param_compatible_contravariant: direct tests
# ===================================================================


def test_contravariant_parent_empty() -> None:
    assert (
        StrictABCMeta._is_param_compatible_contravariant(
            inspect.Parameter.empty,
            int,
        )
        is True
    )


def test_contravariant_child_empty() -> None:
    assert (
        StrictABCMeta._is_param_compatible_contravariant(
            int,
            inspect.Parameter.empty,
        )
        is False
    )


def test_contravariant_child_any() -> None:
    assert StrictABCMeta._is_param_compatible_contravariant(int, Any) is True


def test_contravariant_child_object() -> None:
    assert StrictABCMeta._is_param_compatible_contravariant(int, object) is True


def test_contravariant_parent_any() -> None:
    assert StrictABCMeta._is_param_compatible_contravariant(Any, int) is True


def test_contravariant_exact() -> None:
    assert StrictABCMeta._is_param_compatible_contravariant(int, int) is True


def test_contravariant_issubclass_typeerror() -> None:
    class EvilMeta(type):
        def __subclasscheck__(cls, subclass: Any) -> bool:
            raise TypeError

    class Evil(metaclass=EvilMeta):
        pass

    assert StrictABCMeta._is_param_compatible_contravariant(Evil, int) is False


def test_contravariant_typing_union() -> None:
    assert (
        StrictABCMeta._is_param_compatible_contravariant(
            int,
            int | str,
        )
        is True
    )


def test_contravariant_typing_union_not_containing() -> None:
    assert (
        StrictABCMeta._is_param_compatible_contravariant(
            bytes,
            int | str,
        )
        is False
    )
    