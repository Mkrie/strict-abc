"""Public API and metaclass integration tests."""

import abc
import warnings
from abc import ABC, abstractmethod
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


def test_deep_subclass_override_is_validated() -> None:
    class Base(StrictABC):
        @abstractmethod
        def m(self, a: int = 1) -> None: ...

    class Middle(Base):
        def m(self, a: int = 1) -> None: ...

    with pytest.raises(TypeError, match="removing default value"):
        class _Impl(Middle):
            def m(self, a: int) -> None: ...


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


def test_lsp_exempt_under_staticmethod_skips_validation() -> None:
    class Base(StrictABC):
        @staticmethod
        @abstractmethod
        def m(x: int = 1) -> int: ...

    class Impl(Base):
        @staticmethod
        @lsp_exempt
        def m(x: int) -> int:
            return x

    assert Impl.m(1) == 1


def test_lsp_exempt_under_classmethod_skips_validation() -> None:
    class Base(StrictABC):
        @classmethod
        @abstractmethod
        def m(cls, x: int = 1) -> int: ...

    class Impl(Base):
        @classmethod
        @lsp_exempt
        def m(cls, x: int) -> int:
            return x

    assert Impl.m(1) == 1


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
