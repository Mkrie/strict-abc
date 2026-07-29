from abc import abstractmethod
from pathlib import Path
from typing import Any

import pytest

import strict_abc
from strict_abc import StrictABC, StrictABCMeta, __version__


def test_version_is_string() -> None:
    assert isinstance(__version__, str)


def test_exports() -> None:
    assert set(strict_abc.__all__) == {
        "DescriptorKind",
        "StrictABC",
        "StrictABCMeta",
        "StrictOptions",
        "__version__",
    }


def test_py_typed_exists() -> None:
    assert strict_abc.__file__ is not None
    package_dir = Path(strict_abc.__file__).parent
    assert (package_dir / "py.typed").exists()


def test_strict_abc_without_abstract_methods_can_be_instantiated() -> None:
    class Concrete(StrictABC):
        pass

    Concrete()


def test_abstract_class_cannot_be_instantiated() -> None:
    class Base(StrictABC):
        @abstractmethod
        def m(self) -> None:
            ...

    with pytest.raises(TypeError):
        Base()


def test_valid_concrete_subclass() -> None:
    class Base(StrictABC):
        @abstractmethod
        def m(self, a: int, b: int = 1) -> int:
            ...

    class Impl(Base):
        def m(self, a: int, b: int = 1) -> int:
            return a + b

    assert Impl().m(1) == 2
    assert Impl().m(1, 2) == 3


def test_removing_default_raises() -> None:
    class Base(StrictABC):
        @abstractmethod
        def m(self, a: int, b: int = 1) -> int:
            ...

    with pytest.raises(TypeError, match="removing default value"):
        class _Impl(Base):
            def m(self, a: int, b: int) -> int:
                return a + b


def test_adding_default_allowed() -> None:
    class Base(StrictABC):
        @abstractmethod
        def m(self, a: int) -> int:
            ...

    class Impl(Base):
        def m(self, a: int = 5) -> int:
            return a

    assert Impl().m() == 5


def test_adding_optional_parameter_without_variadic_allowed() -> None:
    class Base(StrictABC):
        @abstractmethod
        def m(self, a: int) -> int:
            ...

    class Impl(Base):
        def m(self, a: int, b: int = 0) -> int:
            return a + b

    assert Impl().m(1) == 1
    assert Impl().m(1, 2) == 3


def test_adding_required_parameter_without_variadic_raises() -> None:
    class Base(StrictABC):
        @abstractmethod
        def m(self, a: int) -> int:
            ...

    with pytest.raises(TypeError, match="new required parameter 'b'"):
        class _Impl(Base):
            def m(self, a: int, b: int) -> int:
                return a + b


def test_fewer_positional_parameters_raises() -> None:
    class Base(StrictABC):
        @abstractmethod
        def m(self, a: int, b: int) -> int:
            ...

    with pytest.raises(TypeError, match=r"without \*args"):
        class _Impl(Base):
            def m(self, a: int) -> int:
                return a


def test_check_names_enabled_raises() -> None:
    class Base(StrictABC):
        __strict_options__ = {"check_names": True}

        @abstractmethod
        def m(self, alpha: int) -> int:
            ...

    with pytest.raises(TypeError, match="parameter name mismatch"):
        class _Impl(Base):
            def m(self, beta: int) -> int:
                return beta


def test_check_names_disabled_allows_rename_positional_only() -> None:
    class Base(StrictABC):
        @abstractmethod
        def m(self, alpha: int, /) -> int:
            ...

    class Impl(Base):
        def m(self, beta: int) -> int:
            return beta

    assert Impl().m(1) == 1


def test_check_names_enabled_raises_for_positional_only() -> None:
    class Base(StrictABC):
        __strict_options__ = {"check_names": True}

        @abstractmethod
        def m(self, alpha: int, /) -> int:
            ...

    with pytest.raises(TypeError, match="parameter name mismatch"):
        class _Impl(Base):
            def m(self, beta: int) -> int:
                return beta


def test_positional_or_keyword_rename_raises_by_default() -> None:
    class Base(StrictABC):
        @abstractmethod
        def m(self, a: int) -> int:
            ...

    with pytest.raises(TypeError, match="cannot accept parent keyword parameter"):
        class _Impl(Base):
            def m(self, b: int) -> int:
                return b


def test_positional_or_keyword_rename_with_kwargs_and_default_allowed() -> None:
    class Base(StrictABC):
        @abstractmethod
        def m(self, a: int) -> int:
            ...

    class Impl(Base):
        def m(self, b: int = 0, **kwargs: int) -> int:
            return int(kwargs.get("a", b))

    assert Impl().m(1) == 1
    assert Impl().m(a=2) == 2


def test_positional_or_keyword_rename_with_kwargs_required_raises() -> None:
    class Base(StrictABC):
        @abstractmethod
        def m(self, a: int) -> int:
            ...

    with pytest.raises(TypeError, match="has no default"):
        class _Impl(Base):
            def m(self, b: int, **kwargs: int) -> int:
                return b


def test_keyword_only_rename_raises_by_default() -> None:
    class Base(StrictABC):
        @abstractmethod
        def m(self, *, a: int) -> int:
            ...

    with pytest.raises(TypeError, match="cannot accept parent keyword parameter"):
        class _Impl(Base):
            def m(self, *, b: int) -> int:
                return b


def test_keyword_only_reorder_allowed() -> None:
    class Base(StrictABC):
        @abstractmethod
        def m(self, *, a: int, b: int = 1) -> int:
            ...

    class Impl(Base):
        def m(self, *, b: int = 1, a: int) -> int:
            return a + b

    assert Impl().m(a=1) == 2
    assert Impl().m(a=1, b=2) == 3


def test_keyword_only_required_as_positional_or_keyword_required_allowed() -> None:
    class Base(StrictABC):
        @abstractmethod
        def m(self, *, a: int) -> int:
            ...

    class Impl(Base):
        def m(self, a: int) -> int:
            return a

    assert Impl().m(a=1) == 1


def test_keyword_only_required_as_positional_only_required_raises() -> None:
    class Base(StrictABC):
        @abstractmethod
        def m(self, *, a: int) -> int:
            ...

    with pytest.raises(TypeError, match="new required parameter 'a'"):
        class _Impl(Base):
            def m(self, a: int, /) -> int:
                return a


def test_optional_positional_before_keyword_only_allowed() -> None:
    class Base(StrictABC):
        @abstractmethod
        def m(self, *, a: int) -> int:
            ...

    class Impl(Base):
        def m(self, x: int = 0, *args: int, a: int) -> int:
            return a + x + sum(args)

    assert Impl().m(a=1) == 1
    assert Impl().m(10, 20, a=1) == 31


def test_positional_or_keyword_to_keyword_only_without_varargs_raises() -> None:
    class Base(StrictABC):
        @abstractmethod
        def m(self, a: int) -> int:
            ...

    with pytest.raises(TypeError, match=r"without \*args"):
        class _Impl(Base):
            def m(self, *, a: int) -> int:
                return a


def test_positional_or_keyword_to_keyword_only_with_varargs_required_raises() -> None:
    class Base(StrictABC):
        @abstractmethod
        def m(self, a: int) -> int:
            ...

    with pytest.raises(TypeError, match="must have a default value"):
        class _Impl(Base):
            def m(self, *args: int, a: int) -> int:
                return a


def test_positional_or_keyword_to_keyword_only_with_varargs_default_allowed() -> None:
    class Base(StrictABC):
        @abstractmethod
        def m(self, a: int) -> int:
            ...

    class Impl(Base):
        def m(self, *args: int, a: int = 1) -> int:
            return a + sum(args)

    # positional call puts 1 into *args, keyword-only `a` stays default
    assert Impl().m(1) == 2

    # keyword call explicitly sets `a`
    assert Impl().m(a=2) == 2


def test_check_types_enabled_missing_annotation_raises() -> None:
    class Base(StrictABC):
        __strict_options__ = {"check_types": True}

        @abstractmethod
        def m(self, a: int) -> int:
            ...

    with pytest.raises(TypeError, match="missing type annotation"):
        class _Impl(Base):
            def m(self, a):
                return a


def test_check_types_enabled_mismatch_raises() -> None:
    class Base(StrictABC):
        __strict_options__ = {"check_types": True}

        @abstractmethod
        def m(self, a: int) -> int:
            ...

    with pytest.raises(TypeError, match="type annotation mismatch"):
        class _Impl(Base):
            def m(self, a: str) -> int:
                return "x"


def test_check_types_enabled_exact_allowed() -> None:
    class Base(StrictABC):
        __strict_options__ = {"check_types": True}

        @abstractmethod
        def m(self, a: int) -> int:
            ...

    class Impl(Base):
        def m(self, a: int) -> int:
            return a

    assert Impl().m(1) == 1


def test_check_types_disabled_allows_mismatch() -> None:
    class Base(StrictABC):
        @abstractmethod
        def m(self, a: int) -> int:
            ...

    class Impl(Base):
        def m(self, a: str) -> int:
            return "x"

    assert Impl().m("1") == "x"


def test_return_type_covariance_allowed() -> None:
    class Base(StrictABC):
        __strict_options__ = {"check_return_type": True}

        @abstractmethod
        def m(self) -> object:
            ...

    class Impl(Base):
        def m(self) -> str:
            return "ok"

    assert Impl().m() == "ok"


def test_return_type_bool_int_allowed() -> None:
    class Base(StrictABC):
        __strict_options__ = {"check_return_type": True}

        @abstractmethod
        def m(self) -> int:
            ...

    class Impl(Base):
        def m(self) -> bool:
            return True

    assert Impl().m() is True


def test_return_type_not_covariant_raises() -> None:
    class Base(StrictABC):
        __strict_options__ = {"check_return_type": True}

        @abstractmethod
        def m(self) -> str:
            ...

    with pytest.raises(TypeError, match="return type not covariant"):
        class _Impl(Base):
            def m(self) -> object:
                return object()


def test_return_type_missing_annotation_raises() -> None:
    class Base(StrictABC):
        __strict_options__ = {"check_return_type": True}

        @abstractmethod
        def m(self) -> int:
            ...

    with pytest.raises(TypeError, match="missing return type annotation"):
        class _Impl(Base):
            def m(self):
                return 1


def test_return_type_disabled_allows_any() -> None:
    class Base(StrictABC):
        @abstractmethod
        def m(self) -> int:
            ...

    class Impl(Base):
        def m(self) -> str:
            return "x"

    assert Impl().m() == "x"


def test_return_type_none_covariant_allowed() -> None:
    class Base(StrictABC):
        __strict_options__ = {"check_return_type": True}

        @abstractmethod
        def m(self) -> object:
            ...

    class Impl(Base):
        def m(self) -> None:
            return None

    assert Impl().m() is None


def test_return_type_any_allowed() -> None:
    class Base1(StrictABC):
        __strict_options__ = {"check_return_type": True}

        @abstractmethod
        def m(self) -> Any:
            ...

    class Impl1(Base1):
        def m(self) -> str:
            return "ok"

    assert Impl1().m() == "ok"

    class Base2(StrictABC):
        __strict_options__ = {"check_return_type": True}

        @abstractmethod
        def m(self) -> str:
            ...

    class Impl2(Base2):
        def m(self) -> Any:
            return "ok"

    assert Impl2().m() == "ok"


def test_staticmethod_valid() -> None:
    class Base(StrictABC):
        @staticmethod
        @abstractmethod
        def m(x: int) -> int:
            ...

    class Impl(Base):
        @staticmethod
        def m(x: int) -> int:
            return x

    assert Impl.m(2) == 2


def test_staticmethod_descriptor_mismatch_raises() -> None:
    class Base(StrictABC):
        @staticmethod
        @abstractmethod
        def m(x: int) -> int:
            ...

    with pytest.raises(TypeError, match="descriptor type mismatch"):
        class _Impl(Base):
            def m(self, x: int) -> int:
                return x


def test_classmethod_valid() -> None:
    class Base(StrictABC):
        @classmethod
        @abstractmethod
        def m(cls, x: int) -> int:
            ...

    class Impl(Base):
        @classmethod
        def m(cls, x: int) -> int:
            return x

    assert Impl.m(3) == 3


def test_classmethod_descriptor_mismatch_raises() -> None:
    class Base(StrictABC):
        @classmethod
        @abstractmethod
        def m(cls, x: int) -> int:
            ...

    with pytest.raises(TypeError, match="descriptor type mismatch"):
        class _Impl(Base):
            @staticmethod
            def m(x: int) -> int:
                return x


def test_parent_var_positional_child_fixed_raises() -> None:
    class Base(StrictABC):
        @abstractmethod
        def m(self, *args: int) -> None:
            ...

    with pytest.raises(TypeError, match=r"removed \*args"):
        class _Impl(Base):
            def m(self) -> None:
                ...


def test_parent_var_keyword_child_fixed_raises() -> None:
    class Base(StrictABC):
        @abstractmethod
        def m(self, **kwargs: int) -> None:
            ...

    with pytest.raises(TypeError, match=r"removed \*\*kwargs"):
        class _Impl(Base):
            def m(self) -> None:
                ...


def test_parent_both_child_missing_kwargs_raises() -> None:
    class Base(StrictABC):
        @abstractmethod
        def m(self, *args: int, **kwargs: int) -> None:
            ...

    with pytest.raises(TypeError, match=r"removed \*\*kwargs"):
        class _Impl(Base):
            def m(self, *args: int) -> None:
                ...


def test_parent_fixed_child_adds_varargs_allowed() -> None:
    class Base(StrictABC):
        @abstractmethod
        def m(self, a: int) -> int:
            ...

    class Impl(Base):
        def m(self, a: int, *args: int) -> int:
            return a + sum(args)

    assert Impl().m(1, 2, 3) == 6


def test_parent_fixed_child_adds_kwargs_allowed() -> None:
    class Base(StrictABC):
        @abstractmethod
        def m(self, a: int) -> int:
            ...

    class Impl(Base):
        def m(self, a: int, **kwargs: int) -> int:
            return a + sum(kwargs.values())

    assert Impl().m(1, b=2) == 3


def test_parent_varargs_child_varargs_kwargs_allowed() -> None:
    class Base(StrictABC):
        @abstractmethod
        def m(self, *args: int) -> None:
            ...

    class Impl(Base):
        def m(self, *args: int, **kwargs: int) -> None:
            ...

    Impl().m(1, x=2)


def test_parent_varargs_child_required_extra_raises() -> None:
    class Base(StrictABC):
        @abstractmethod
        def m(self, *args: int) -> None:
            ...

    with pytest.raises(TypeError, match="new required parameter 'a'"):
        class _Impl(Base):
            def m(self, a: int, *args: int) -> None:
                ...


def test_parent_varargs_child_optional_extra_allowed() -> None:
    class Base(StrictABC):
        @abstractmethod
        def m(self, *args: int) -> int:
            ...

    class Impl(Base):
        def m(self, a: int = 1, *args: int) -> int:
            return a + sum(args)

    assert Impl().m() == 1
    assert Impl().m(5) == 5


def test_parent_varargs_child_removes_default_on_existing_raises() -> None:
    class Base(StrictABC):
        @abstractmethod
        def m(self, a: int = 1, *args: int) -> int:
            ...

    with pytest.raises(TypeError, match="removing default value"):
        class _Impl(Base):
            def m(self, a: int, *args: int) -> int:
                return a


def test_parent_keyword_only_missing_without_kwargs_raises() -> None:
    class Base(StrictABC):
        @abstractmethod
        def m(self, a: int, *, b: int = 1) -> int:
            ...

    with pytest.raises(TypeError, match="cannot accept parent keyword parameter 'b'"):
        class _Impl(Base):
            def m(self, a: int, *args: int) -> int:
                return a


def test_parent_keyword_only_absorbed_by_kwargs_allowed() -> None:
    class Base(StrictABC):
        @abstractmethod
        def m(self, a: int, *, b: int = 1) -> int:
            ...

    class Impl(Base):
        def m(self, a: int, *args: int, **kwargs: int) -> int:
            return a + int(kwargs.get("b", 0))

    assert Impl().m(1, b=2) == 3


def test_missing_positional_or_keyword_keyword_requires_kwargs() -> None:
    class Base(StrictABC):
        @abstractmethod
        def m(self, a: int, *args: int) -> int:
            ...

    with pytest.raises(TypeError, match=r"without \*\*kwargs"):
        class _Impl(Base):
            def m(self, *args: int) -> int:
                return sum(args)


def test_missing_positional_or_keyword_absorbed_by_both_variadics_allowed() -> None:
    class Base(StrictABC):
        @abstractmethod
        def m(self, a: int, *args: int) -> int:
            ...

    class Impl(Base):
        def m(self, *args: int, **kwargs: int) -> int:
            return int(kwargs.get("a", 0)) + sum(args)

    assert Impl().m(a=5) == 5


def test_missing_positional_only_absorbed_by_varargs_allowed() -> None:
    class Base(StrictABC):
        @abstractmethod
        def m(self, a: int, /, *args: int) -> int:
            ...

    class Impl(Base):
        def m(self, *args: int) -> int:
            return sum(args)

    assert Impl().m(1, 2) == 3


def test_extra_required_keyword_only_raises() -> None:
    class Base(StrictABC):
        @abstractmethod
        def m(self, a: int, **kwargs: int) -> int:
            ...

    with pytest.raises(TypeError, match="new required keyword-only parameter 'b'"):
        class _Impl(Base):
            def m(self, a: int, *, b: int, **kwargs: int) -> int:
                return a + b


def test_extra_optional_keyword_only_allowed() -> None:
    class Base(StrictABC):
        @abstractmethod
        def m(self, a: int, **kwargs: int) -> int:
            ...

    class Impl(Base):
        def m(self, a: int, *, b: int = 1, **kwargs: int) -> int:
            return a + b + sum(kwargs.values())

    assert Impl().m(1) == 2


def test_positional_only_to_positional_or_keyword_allowed() -> None:
    class Base(StrictABC):
        @abstractmethod
        def m(self, a: int, /) -> int:
            ...

    class Impl(Base):
        def m(self, a: int) -> int:
            return a

    assert Impl().m(1) == 1


def test_positional_or_keyword_to_positional_only_raises() -> None:
    class Base(StrictABC):
        @abstractmethod
        def m(self, a: int) -> int:
            ...

    with pytest.raises(TypeError, match="kind transition"):
        class _Impl(Base):
            def m(self, a: int, /) -> int:
                return a


def test_keyword_only_to_positional_or_keyword_allowed() -> None:
    class Base(StrictABC):
        @abstractmethod
        def m(self, *, a: int) -> int:
            ...

    class Impl(Base):
        def m(self, a: int) -> int:
            return a

    assert Impl().m(a=1) == 1


def test_check_defaults_disabled_allows_removing_default() -> None:
    class Base(StrictABC):
        __strict_options__ = {"check_defaults": False}

        @abstractmethod
        def m(self, a: int = 1) -> int:
            ...

    class Impl(Base):
        def m(self, a: int) -> int:
            return a

    assert Impl().m(2) == 2


def test_options_inherited_from_base() -> None:
    class Base(StrictABC):
        __strict_options__ = {"check_names": True}

        @abstractmethod
        def m(self, alpha: int, /) -> int:
            ...

    with pytest.raises(TypeError, match="parameter name mismatch"):
        class _Impl(Base):
            def m(self, beta: int) -> int:
                return beta


def test_child_can_override_options() -> None:
    class Base(StrictABC):
        __strict_options__ = {"check_names": True}

        @abstractmethod
        def m(self, alpha: int, /) -> int:
            ...

    class Impl(Base):
        __strict_options__ = {"check_names": False}

        def m(self, beta: int) -> int:
            return beta

    assert Impl().m(1) == 1


def test_options_are_merged_from_base_classes() -> None:
    class Base(StrictABC):
        __strict_options__ = {"check_types": True}

        @abstractmethod
        def m(self, a: int) -> int:
            ...

    with pytest.raises(TypeError, match="type annotation mismatch"):
        class _Impl(Base):
            __strict_options__ = {"check_names": True}

            def m(self, a: str) -> int:
                return "x"


def test_can_use_metaclass_directly() -> None:
    class Base(metaclass=StrictABCMeta):
        @abstractmethod
        def m(self) -> int:
            ...

    with pytest.raises(TypeError):
        Base()

    class Impl(Base):
        def m(self) -> int:
            return 1

    assert Impl().m() == 1


def test_subclass_can_keep_method_abstract() -> None:
    class Base(StrictABC):
        @abstractmethod
        def m(self) -> None:
            ...

    class Middle(Base):
        @abstractmethod
        def m(self) -> None:
            ...

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


def test_mixin_inherited_implementation_is_validated() -> None:
    class Base(StrictABC):
        @abstractmethod
        def m(self, a: int = 1) -> None:
            ...

    class Mixin:
        def m(self, a: int) -> None:
            ...

    with pytest.raises(TypeError, match="removing default value"):
        class _Impl(Mixin, Base):
            pass
        
def test_mixin_after_abstract_base_keeps_class_abstract() -> None:
    class Base(StrictABC):
        @abstractmethod
        def m(self, a: int = 1) -> None:
            ...

    class Mixin:
        def m(self, a: int) -> None:
            ...

    class Abstract(Base, Mixin):
        pass

    with pytest.raises(TypeError):
        Abstract()

def test_multiple_abstract_bases_are_validated() -> None:
    class A(StrictABC):
        @abstractmethod
        def m(self, a: int) -> None:
            ...

    class B(StrictABC):
        @abstractmethod
        def m(self, a: int, b: int) -> None:
            ...

    with pytest.raises(TypeError, match=r"without \*args"):
        class _C(A, B):
            def m(self, a: int) -> None:
                ...


def test_abstract_property_to_property_allowed() -> None:
    class Base(StrictABC):
        @property
        @abstractmethod
        def value(self) -> int:
            ...

    class Impl(Base):
        @property
        def value(self) -> int:
            return 1

    assert Impl().value == 1


def test_method_to_property_descriptor_mismatch_raises() -> None:
    class Base(StrictABC):
        @abstractmethod
        def m(self) -> int:
            ...

    with pytest.raises(TypeError, match="descriptor type mismatch"):
        class _Impl(Base):
            @property
            def m(self) -> int:
                return 1


def test_property_to_method_descriptor_mismatch_raises() -> None:
    class Base(StrictABC):
        @property
        @abstractmethod
        def value(self) -> int:
            ...

    with pytest.raises(TypeError, match="descriptor type mismatch"):
        class _Impl(Base):
            def value(self) -> int:
                return 1


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