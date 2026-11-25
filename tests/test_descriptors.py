"""Descriptor and callable introspection tests."""

import asyncio
import functools
import inspect
from abc import abstractmethod
from collections.abc import AsyncIterator, Iterator
from typing import Any

import pytest

from strict_abc import (
    StrictABC,
    StrictABCMeta,
)

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


def test_async_generator_abstract_sync_generator_impl_raises() -> None:
    class Base(StrictABC):
        @abstractmethod
        async def m(self) -> AsyncIterator[int]:
            yield 1

    with pytest.raises(TypeError, match="async/sync mismatch"):

        class _Impl(Base):
            def m(self) -> Iterator[int]:
                yield 1


def test_async_generator_abstract_async_generator_impl_allowed() -> None:
    class Base(StrictABC):
        @abstractmethod
        async def m(self) -> AsyncIterator[int]:
            yield 1

    class Impl(Base):
        async def m(self) -> AsyncIterator[int]:
            yield 1

    async def collect() -> list[int]:
        return [item async for item in Impl().m()]

    assert asyncio.run(collect()) == [1]


def test_async_coroutine_async_generator_impl_raises() -> None:
    class Base(StrictABC):
        @abstractmethod
        async def m(self) -> int: ...

    with pytest.raises(TypeError, match="async/sync mismatch"):

        class _Impl(Base):
            async def m(self) -> AsyncIterator[int]:
                yield 1
