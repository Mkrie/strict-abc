"""Parameter and return type compatibility tests."""

import inspect
import typing
from abc import abstractmethod
from typing import Any

import pytest

from strict_abc import (
    StrictABC,
    StrictABCMeta,
)

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


def test_check_types_variadic_mismatch_raises() -> None:
    class Base(StrictABC):
        __strict_options__ = {"check_types": True}

        @abstractmethod
        def m(self, *args: int, **kwargs: str) -> None: ...

    with pytest.raises(TypeError, match=r"type annotation mismatch for '\*args'"):
        class _Impl(Base):
            def m(self, *args: str, **kwargs: str) -> None: ...


def test_check_types_variadic_missing_annotation_raises() -> None:
    class Base(StrictABC):
        __strict_options__ = {"check_types": True}

        @abstractmethod
        def m(self, *args: int, **kwargs: str) -> None: ...

    with pytest.raises(
        TypeError, match=r"missing type annotation for '\*\*kwargs'"
    ):
        class _Impl(Base):
            def m(self, *args: int, **kwargs) -> None: ...


def test_check_types_keyword_absorbed_by_kwargs_mismatch_raises() -> None:
    class Base(StrictABC):
        __strict_options__ = {"check_types": True}

        @abstractmethod
        def m(self, a: int) -> None: ...

    with pytest.raises(TypeError, match="type annotation mismatch for 'a'"):
        class _Impl(Base):
            def m(self, *args: int, **kwargs: str) -> None: ...


def test_check_types_positional_only_absorbed_by_varargs_mismatch_raises() -> None:
    class Base(StrictABC):
        __strict_options__ = {"check_types": True}

        @abstractmethod
        def m(self, a: int, /) -> None: ...

    with pytest.raises(TypeError, match="type annotation mismatch for 'a'"):
        class _Impl(Base):
            def m(self, *args: str) -> None: ...


def test_check_types_absorbed_parameters_exact_allowed() -> None:
    class Base(StrictABC):
        __strict_options__ = {"check_types": True}

        @abstractmethod
        def m(self, a: int) -> None: ...

    class Impl(Base):
        def m(self, *args: int, **kwargs: int) -> None: ...

    Impl().m(1)
    Impl().m(a=1)


def test_check_types_reordered_later_parameter_mismatch_raises() -> None:
    class Base(StrictABC):
        __strict_options__ = {"check_types": True}

        @abstractmethod
        def m(self, a: int = 0) -> None: ...

    with pytest.raises(TypeError, match="type annotation mismatch for 'a'"):
        class _Impl(Base):
            def m(self, b: int = 1, a: str = 0) -> None: ...


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


def test_contravariant_variadic_widening_allowed() -> None:
    class Base(StrictABC):
        __strict_options__ = {"check_types_contravariant": True}

        @abstractmethod
        def m(self, *args: int, **kwargs: int) -> None: ...

    class Impl(Base):
        def m(self, *args: object, **kwargs: object) -> None: ...

    Impl().m(1, a=2)


def test_contravariant_absorbed_fixed_parameter_widening_allowed() -> None:
    class Base(StrictABC):
        __strict_options__ = {"check_types_contravariant": True}

        @abstractmethod
        def m(self, a: int, /) -> None: ...

    class Impl(Base):
        def m(self, *args: object) -> None: ...

    Impl().m(1)


def test_contravariant_absorbed_fixed_parameter_narrowing_raises() -> None:
    class Base(StrictABC):
        __strict_options__ = {"check_types_contravariant": True}

        @abstractmethod
        def m(self, a: object) -> None: ...

    with pytest.raises(TypeError, match="parameter type for 'a' is not contravariant"):
        class _Impl(Base):
            def m(self, *args: object, **kwargs: int) -> None: ...


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


def test_is_return_compatible_bare_parent_accepts_parameterized_child() -> None:
    # A bare parent type has no generic constraints, so narrowing is valid.
    assert StrictABCMeta._is_return_compatible(list[int], list) is False
    assert StrictABCMeta._is_return_compatible(list, list[int]) is True
    assert StrictABCMeta._is_return_compatible(typing.Sequence, list[int]) is True


def test_is_return_compatible_bare_parent_alias_accepts_bare_child() -> None:
    assert StrictABCMeta._is_return_compatible(typing.List, list) is True  # noqa: UP006
    assert StrictABCMeta._is_return_compatible(typing.Sequence, list) is True
    assert StrictABCMeta._is_return_compatible(typing.Iterable, list) is True
    assert StrictABCMeta._is_return_compatible(typing.Sequence, dict) is False


def test_is_return_compatible_union_subset() -> None:
    assert StrictABCMeta._is_return_compatible(int | str, int) is True
    assert StrictABCMeta._is_return_compatible(int | str, int | str) is True
    assert (
        StrictABCMeta._is_return_compatible(int | str | bytes, int | str) is True
    )
    assert StrictABCMeta._is_return_compatible(int | str, object) is False


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


def test_contravariant_generic_widening() -> None:
    assert (
        StrictABCMeta._is_param_compatible_contravariant(list[int], list)
        is True
    )
    assert (
        StrictABCMeta._is_param_compatible_contravariant(
            list[int], typing.Sequence
        )
        is True
    )
    assert (
        StrictABCMeta._is_param_compatible_contravariant(list, list[int])
        is False
    )


def test_contravariant_parent_union() -> None:
    assert (
        StrictABCMeta._is_param_compatible_contravariant(
            int | str, int | str | float
        )
        is True
    )
    assert (
        StrictABCMeta._is_param_compatible_contravariant(int | str, int)
        is False
    )
