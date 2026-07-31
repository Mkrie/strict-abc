import abc
import inspect
import typing
from abc import abstractmethod
from collections.abc import Mapping
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
        def m(self) -> None: ...

    with pytest.raises(TypeError):
        Base()


def test_valid_concrete_subclass() -> None:
    class Base(StrictABC):
        @abstractmethod
        def m(self, a: int, b: int = 1) -> int: ...

    class Impl(Base):
        def m(self, a: int, b: int = 1) -> int:
            return a + b

    assert Impl().m(1) == 2
    assert Impl().m(1, 2) == 3


def test_removing_default_raises() -> None:
    class Base(StrictABC):
        @abstractmethod
        def m(self, a: int, b: int = 1) -> int: ...

    with pytest.raises(TypeError, match="removing default value"):

        class _Impl(Base):
            def m(self, a: int, b: int) -> int:
                return a + b


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

    # positional call puts 1 into *args, keyword-only `a` stays default
    assert Impl().m(1) == 2

    # keyword call explicitly sets `a`
    assert Impl().m(a=2) == 2


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


def test_check_defaults_disabled_allows_removing_default() -> None:
    class Base(StrictABC):
        __strict_options__ = {"check_defaults": False}

        @abstractmethod
        def m(self, a: int = 1) -> int: ...

    class Impl(Base):
        def m(self, a: int) -> int:
            return a

    assert Impl().m(2) == 2


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


def test_invalid_strict_options_are_ignored() -> None:
    class Base(StrictABC):
        __strict_options__ = ["not-a-dict"]  # type: ignore[assignment]

        @abstractmethod
        def m(self, a: int = 1) -> int: ...

    with pytest.raises(TypeError, match="removing default value"):

        class _Impl(Base):
            def m(self, a: int) -> int:
                return a


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


def test_keyword_only_default_removal_by_name_raises() -> None:
    class Base(StrictABC):
        @abstractmethod
        def m(self, *, a: int = 1) -> int: ...

    with pytest.raises(TypeError, match="removing default value"):

        class _Impl(Base):
            def m(self, *, a: int) -> int:
                return a


def test_parent_abstractmethods_not_frozenset_is_ignored() -> None:
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
    # This branch is almost unreachable in a normal ABC scenario, because
    # ABCMeta always sets a frozenset. Here we patch ABCMeta.__new__
    # to cover the defensive branch.
    def fake_new(mcls, name, bases, namespace, **kwargs):
        Dummy = type("Dummy", (), {})
        Dummy.__abstractmethods__ = ["not-a-frozenset"]  # type: ignore[assignment]
        return Dummy

    monkeypatch.setattr(abc.ABCMeta, "__new__", fake_new)

    cls = StrictABCMeta.__new__(StrictABCMeta, "C", (), {})
    assert cls.__abstractmethods__ == ["not-a-frozenset"]


def test_concrete_attr_reported_abstract_is_skipped(monkeypatch: pytest.MonkeyPatch) -> None:
    # _find_concrete_attr itself filters abstract attributes, so the second
    # part of the condition `or getattr(concrete, "__isabstractmethod__", False)`
    # is unreachable in a normal scenario. We cover it artificially.
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

    # If validation had run, it would raise TypeError due to the new required 'x'.
    assert Impl().m(3) == 3


# ---------------------------------------------------------------------------
# Descriptor kind / unwrap defensive branches
# ---------------------------------------------------------------------------


def test_descriptor_kind_typeerror_on_parent_attr_is_skipped() -> None:
    class NonCallableDescriptor:
        __isabstractmethod__ = True

        def __get__(self, obj, objtype=None):
            return self

    class Base(StrictABC):
        m = NonCallableDescriptor()

    class Impl(Base):
        m = 1

    Impl()


def test_descriptor_kind_typeerror_on_child_attr_is_skipped() -> None:
    class Base(StrictABC):
        @abstractmethod
        def m(self) -> int: ...

    class Impl(Base):
        m = 1

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
    def f(self):
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
    def f(self):
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

    # This will raise TypeError inside _descriptor_kind.
    with pytest.raises(TypeError, match="Unsupported descriptor type"):
        StrictABCMeta._unwrap_descriptor(1)


def test_unwrap_descriptor_final_defensive_raise(monkeypatch: pytest.MonkeyPatch) -> None:
    # The final raise in _unwrap_descriptor is practically unreachable, because
    # _descriptor_kind already raises TypeError for unsupported objects.
    # We cover it artificially.
    monkeypatch.setattr(StrictABCMeta, "_descriptor_kind", lambda attr: "instancemethod")

    with pytest.raises(TypeError, match="Unsupported descriptor type"):
        StrictABCMeta._unwrap_descriptor(1)


# ---------------------------------------------------------------------------
# Signature fallback
# ---------------------------------------------------------------------------


def test_signature_falls_back_when_eval_str_fails() -> None:
    def f(x: "UndefinedAnnotation") -> "UndefinedAnnotation":  # noqa: F821
        return x

    sig = StrictABCMeta._signature(f)

    assert isinstance(sig, inspect.Signature)
    assert sig.parameters["x"].annotation == "UndefinedAnnotation"


def test_signature_name_error_is_swallowed_during_class_creation() -> None:
    class NameErrorSignature:
        __isabstractmethod__ = True

        def __call__(self):
            return None

        @property
        def __signature__(self):
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

        def __call__(self):
            return None

        @property
        def __signature__(self):
            raise ValueError("boom")

    class ConcreteValueErrorSignature(ValueErrorSignature):
        __isabstractmethod__ = False

    class Base(StrictABC):
        m = ValueErrorSignature()

    class Impl(Base):
        m = ConcreteValueErrorSignature()

    Impl()


# ---------------------------------------------------------------------------
# _is_return_compatible: rare and defensive branches
# ---------------------------------------------------------------------------


def test_is_return_compatible_parent_empty() -> None:
    assert StrictABCMeta._is_return_compatible(inspect.Signature.empty, int) is True


def test_is_return_compatible_child_empty() -> None:
    assert StrictABCMeta._is_return_compatible(int, inspect.Signature.empty) is False


def test_is_return_compatible_none() -> None:
    assert StrictABCMeta._is_return_compatible(None, None) is True


def test_is_return_compatible_issubclass_typeerror() -> None:
    class EvilMeta(type):
        def __subclasscheck__(cls, subclass):
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
        def __subclasscheck__(cls, subclass):
            raise TypeError

    class EvilOrigin(metaclass=EvilMeta):
        pass

    class FakeGeneric:
        def __init__(self, origin, args):
            self.__origin__ = origin
            self.__args__ = args

        def __eq__(self, other):
            return False

    p = FakeGeneric(EvilOrigin, (int,))
    c = FakeGeneric(list, (int,))

    assert StrictABCMeta._is_return_compatible(p, c) is False


def test_is_return_compatible_generic_equality_second_check() -> None:
    # Covers the rare branch of the second `p == c` check inside the generic block.
    class ToggleEqGeneric:
        def __init__(self, origin, args):
            self.__origin__ = origin
            self.__args__ = args
            self._first = True

        def __eq__(self, other):
            if self._first:
                self._first = False
                return False
            return True

    p = ToggleEqGeneric(list, (int,))
    c = ToggleEqGeneric(list, (int,))

    assert StrictABCMeta._is_return_compatible(p, c) is True


# ---------------------------------------------------------------------------
# _validate_signature: direct tests for rare branches
# ---------------------------------------------------------------------------


def test_validate_signature_descriptor_mismatch_direct() -> None:
    sig = inspect.signature(lambda: None)

    with pytest.raises(TypeError, match="descriptor type mismatch"):
        StrictABCMeta._validate_signature(
            meth_name="m",
            sig_parent=sig,
            sig_child=sig,
            parent_descriptor="staticmethod",
            child_descriptor="instancemethod",
            check_names=False,
            check_defaults=True,
            check_types=False,
            check_return_type=False,
            class_name="C",
        )


def test_validate_signature_handles_empty_params_for_non_static() -> None:
    sig = inspect.signature(lambda: None)

    # Should not fail: p_params and c_params are empty,
    # but the descriptor is not a staticmethod.
    StrictABCMeta._validate_signature(
        meth_name="m",
        sig_parent=sig,
        sig_child=sig,
        parent_descriptor="instancemethod",
        child_descriptor="instancemethod",
        check_names=False,
        check_defaults=True,
        check_types=False,
        check_return_type=False,
        class_name="C",
    )


# ---------------------------------------------------------------------------
# check_types: additional branches
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# check_defaults: keyword-only branch
# ---------------------------------------------------------------------------


def test_check_defaults_disabled_allows_removing_keyword_only_default() -> None:
    class Base(StrictABC):
        __strict_options__ = {"check_defaults": False}

        @abstractmethod
        def m(self, *, a: int = 1) -> int: ...

    class Impl(Base):
        def m(self, *, a: int) -> int:
            return a

    assert Impl().m(a=2) == 2


# ---------------------------------------------------------------------------
# check_return_type: parent empty / None
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Additional LSP combinations
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Private helpers: _find_concrete_attr / _find_abstract_attrs
# ---------------------------------------------------------------------------


def test_find_concrete_attr_skips_abstract_before_concrete() -> None:
    class Base(StrictABC):
        @abstractmethod
        def m(self) -> int: ...

    class Mixin:
        def m(self) -> int:
            return 1

    class C(Base, Mixin):
        pass

    # The class remains abstract because Base comes before Mixin.
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


# ---------------------------------------------------------------------------
# Options: Mapping / non-Mapping
# ---------------------------------------------------------------------------


def test_options_mapping_non_dict_is_accepted() -> None:
    class OptionsMapping(Mapping):
        def __init__(self, data):
            self._data = data

        def __getitem__(self, key):
            return self._data[key]

        def __iter__(self):
            return iter(self._data)

        def __len__(self):
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
