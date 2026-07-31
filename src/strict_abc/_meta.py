from __future__ import annotations

import inspect
from abc import ABC, ABCMeta
from collections.abc import Callable, Mapping
from typing import Any, ClassVar, Literal, TypedDict, cast

__all__ = [
    "StrictABC",
    "StrictABCMeta",
    "StrictOptions",
    "DescriptorKind",
]


DescriptorKind = Literal[
    "staticmethod",
    "classmethod",
    "property",
    "instancemethod",
]


class StrictOptions(TypedDict, total=False):
    """Options accepted by ``StrictABCMeta``."""

    check_names: bool
    check_defaults: bool
    check_types: bool
    check_return_type: bool


class StrictABCMeta(ABCMeta):
    """Enforce LSP-friendly signatures for concrete implementations of abstract methods.

    Options are read from ``__strict_options__`` and merged across the MRO.

    Supported options:

    * ``check_names``: require equal parameter names.
    * ``check_defaults``: forbid removing default values.
    * ``check_types``: require exact parameter type annotations.
    * ``check_return_type``: require covariant return type annotations.
    """

    def __new__(
        mcls: type[StrictABCMeta],
        name: str,
        bases: tuple[type[Any], ...],
        namespace: dict[str, Any],
        **kwargs: Any,
    ) -> type[Any]:
        cls: type[Any] = super().__new__(mcls, name, bases, namespace, **kwargs)

        options: StrictOptions = mcls._get_options(cls)

        check_names: bool = bool(options.get("check_names", False))
        check_defaults: bool = bool(options.get("check_defaults", True))
        check_types: bool = bool(options.get("check_types", False))
        check_return_type: bool = bool(options.get("check_return_type", False))

        parent_abstracts: set[str] = set()

        for base in bases:
            abstract_methods: object = getattr(base, "__abstractmethods__", frozenset())
            if isinstance(abstract_methods, frozenset):
                parent_abstracts.update(cast(frozenset[str], abstract_methods))

        cls_abstracts_object: object = getattr(cls, "__abstractmethods__", frozenset())
        cls_abstracts: frozenset[str] = (
            cast(frozenset[str], cls_abstracts_object)
            if isinstance(cls_abstracts_object, frozenset)
            else frozenset()
        )

        for meth_name in parent_abstracts:
            # If the method is still abstract in the current class, there is
            # nothing concrete to validate yet.
            if meth_name in cls_abstracts:
                continue

            concrete = mcls._find_concrete_attr(cls, meth_name)
            if concrete is None or bool(getattr(concrete, "__isabstractmethod__", False)):
                continue

            abstract_attrs = mcls._find_abstract_attrs(cls, meth_name)

            for parent_attr in abstract_attrs:
                try:
                    parent_kind = mcls._descriptor_kind(parent_attr)
                    child_kind = mcls._descriptor_kind(concrete)
                except TypeError:
                    continue

                if parent_kind != child_kind:
                    raise TypeError(
                        f"{cls.__name__}.{meth_name}: descriptor type mismatch "
                        f"(expected {parent_kind}, got {child_kind})"
                    )

                try:
                    parent_func, _ = mcls._unwrap_descriptor(parent_attr)
                    child_func, _ = mcls._unwrap_descriptor(concrete)

                    sig_parent: inspect.Signature = mcls._signature(parent_func)
                    sig_child: inspect.Signature = mcls._signature(child_func)
                except (TypeError, ValueError, NameError):
                    continue

                mcls._validate_signature(
                    meth_name=meth_name,
                    sig_parent=sig_parent,
                    sig_child=sig_child,
                    parent_descriptor=parent_kind,
                    child_descriptor=child_kind,
                    check_names=check_names,
                    check_defaults=check_defaults,
                    check_types=check_types,
                    check_return_type=check_return_type,
                    class_name=cls.__name__,
                )

        return cls

    @staticmethod
    def _get_options(cls: type[Any]) -> StrictOptions:
        resolved: dict[str, object] = {}

        # Merge options through the MRO so subclasses can override only part
        # of the configuration instead of replacing the whole dict accidentally.
        for base in reversed(cls.__mro__):
            raw: object = base.__dict__.get("__strict_options__")
            if isinstance(raw, Mapping):
                resolved.update(cast(Mapping[str, object], raw))

        return {
            "check_names": bool(resolved.get("check_names", False)),
            "check_defaults": bool(resolved.get("check_defaults", True)),
            "check_types": bool(resolved.get("check_types", False)),
            "check_return_type": bool(resolved.get("check_return_type", False)),
        }

    @staticmethod
    def _find_concrete_attr(cls: type[Any], name: str) -> object | None:
        for base in cls.__mro__:
            attr: object = base.__dict__.get(name)
            if attr is not None and not bool(getattr(attr, "__isabstractmethod__", False)):
                return attr
        return None

    @staticmethod
    def _find_abstract_attrs(cls: type[Any], name: str) -> list[object]:
        attrs: list[object] = []
        seen: set[int] = set()

        for base in cls.__mro__[1:]:
            attr: object = base.__dict__.get(name)
            if attr is not None and bool(getattr(attr, "__isabstractmethod__", False)):
                attr_id = id(attr)
                if attr_id not in seen:
                    attrs.append(attr)
                    seen.add(attr_id)

        return attrs

    @staticmethod
    def _descriptor_kind(attr: object) -> DescriptorKind:
        if isinstance(attr, property):
            return "property"
        if isinstance(attr, staticmethod):
            return "staticmethod"
        if isinstance(attr, classmethod):
            return "classmethod"
        if callable(attr):
            return "instancemethod"
        raise TypeError("Unsupported descriptor type")

    @staticmethod
    def _unwrap_descriptor(attr: object) -> tuple[Callable[..., Any], DescriptorKind]:
        kind = StrictABCMeta._descriptor_kind(attr)

        if isinstance(attr, property):
            if attr.fget is None:
                raise TypeError("Property without getter cannot be inspected")
            return attr.fget, kind

        if isinstance(attr, staticmethod):
            return attr.__func__, kind

        if isinstance(attr, classmethod):
            return attr.__func__, kind

        if callable(attr):
            return attr, kind

        raise TypeError("Unsupported descriptor type")

    @staticmethod
    def _signature(func: Callable[..., Any]) -> inspect.Signature:
        # Prefer evaluated annotations when possible. This helps with
        # `from __future__ import annotations` in user code.
        try:
            return inspect.signature(func, eval_str=True)
        except Exception:
            return inspect.signature(func)

    @staticmethod
    def _normalize_annotation(annotation: object) -> object:
        if annotation is None:
            return type(None)
        return annotation

    @staticmethod
    def _is_return_compatible(parent_ret: object, child_ret: object) -> bool:
        if parent_ret is inspect.Signature.empty:
            return True

        if child_ret is inspect.Signature.empty:
            return False

        p = StrictABCMeta._normalize_annotation(parent_ret)
        c = StrictABCMeta._normalize_annotation(child_ret)

        if p is Any or c is Any:
            return True

        if p == c:
            return True

        # Everything is compatible with `object` at runtime.
        if p is object:
            return True

        if isinstance(p, type) and isinstance(c, type):
            try:
                return issubclass(c, p)
            except TypeError:
                return False

        # Very small and conservative helper for generic aliases.
        p_origin = getattr(p, "__origin__", None)
        c_origin = getattr(c, "__origin__", None)

        if p_origin is not None and c_origin is not None:
            if p == c:
                return True

            if isinstance(p_origin, type) and isinstance(c_origin, type):
                try:
                    if issubclass(c_origin, p_origin):
                        return getattr(p, "__args__", None) == getattr(c, "__args__", None)
                except TypeError:
                    return False

        return False

    @staticmethod
    def _validate_signature(
        meth_name: str,
        sig_parent: inspect.Signature,
        sig_child: inspect.Signature,
        parent_descriptor: DescriptorKind,
        child_descriptor: DescriptorKind,
        check_names: bool,
        check_defaults: bool,
        check_types: bool,
        check_return_type: bool,
        class_name: str,
    ) -> None:
        if parent_descriptor != child_descriptor:
            raise TypeError(
                f"{class_name}.{meth_name}: descriptor type mismatch "
                f"(expected {parent_descriptor}, got {child_descriptor})"
            )

        p_params: list[inspect.Parameter] = list(sig_parent.parameters.values())
        c_params: list[inspect.Parameter] = list(sig_child.parameters.values())

        if parent_descriptor != "staticmethod" and p_params:
            p_params = p_params[1:]

        if child_descriptor != "staticmethod" and c_params:
            c_params = c_params[1:]

        p_has_var_pos: bool = any(p.kind == inspect.Parameter.VAR_POSITIONAL for p in p_params)
        p_has_var_kw: bool = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in p_params)
        c_has_var_pos: bool = any(c.kind == inspect.Parameter.VAR_POSITIONAL for c in c_params)
        c_has_var_kw: bool = any(c.kind == inspect.Parameter.VAR_KEYWORD for c in c_params)

        if p_has_var_pos and not c_has_var_pos:
            raise TypeError(
                f"{class_name}.{meth_name}: removed *args from parent signature (violates LSP)"
            )

        if p_has_var_kw and not c_has_var_kw:
            raise TypeError(
                f"{class_name}.{meth_name}: removed **kwargs from parent signature (violates LSP)"
            )

        positional_kinds = (
            inspect.Parameter.POSITIONAL_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
        )
        keyword_accessible_kinds = (
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            inspect.Parameter.KEYWORD_ONLY,
        )

        p_pos: list[inspect.Parameter] = [p for p in p_params if p.kind in positional_kinds]
        c_pos: list[inspect.Parameter] = [c for c in c_params if c.kind in positional_kinds]

        p_kw: dict[str, inspect.Parameter] = {
            p.name: p for p in p_params if p.kind == inspect.Parameter.KEYWORD_ONLY
        }
        c_kw: dict[str, inspect.Parameter] = {
            c.name: c for c in c_params if c.kind == inspect.Parameter.KEYWORD_ONLY
        }

        c_by_name_keyword: dict[str, inspect.Parameter] = {
            c.name: c for c in c_params if c.kind in keyword_accessible_kinds
        }

        # ------------------------------------------------------------------
        # Positional compatibility.
        # ------------------------------------------------------------------

        if len(c_pos) < len(p_pos) and not c_has_var_pos:
            raise TypeError(
                f"{class_name}.{meth_name}: cannot accept parent positional "
                f"parameters without *args"
            )

        allowed_kind_expansions = {
            (
                inspect.Parameter.POSITIONAL_ONLY,
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
            ),
        }

        for p, c in zip(p_pos, c_pos, strict=False):
            if check_defaults:
                p_has_default: bool = p.default is not inspect.Parameter.empty
                c_has_default: bool = c.default is not inspect.Parameter.empty

                if p_has_default and not c_has_default:
                    raise TypeError(
                        f"{class_name}.{meth_name}: removing default value for "
                        f"'{p.name}' strengthens precondition and violates LSP"
                    )

            if p.kind != c.kind and (p.kind, c.kind) not in allowed_kind_expansions:
                raise TypeError(
                    f"{class_name}.{meth_name}: parameter '{p.name}' kind transition "
                    f"{p.kind.name} -> {c.kind.name} restricts call syntax and violates LSP"
                )

            if check_names and p.name != c.name:
                raise TypeError(
                    f"{class_name}.{meth_name}: parameter name mismatch "
                    f"(expected '{p.name}', got '{c.name}')"
                )

            # Even when check_names=False, names of positional-or-keyword
            # parameters are part of the keyword-call contract.
            if p.kind == inspect.Parameter.POSITIONAL_OR_KEYWORD and p.name != c.name:
                if not c_has_var_kw:
                    raise TypeError(
                        f"{class_name}.{meth_name}: cannot accept parent keyword "
                        f"parameter '{p.name}' without **kwargs"
                    )

                if c.default is inspect.Parameter.empty:
                    raise TypeError(
                        f"{class_name}.{meth_name}: cannot accept parent keyword "
                        f"parameter '{p.name}' because corresponding child "
                        f"parameter has no default"
                    )

            if check_types:
                p_has_annotation: bool = p.annotation is not inspect.Parameter.empty
                c_has_annotation: bool = c.annotation is not inspect.Parameter.empty

                if p_has_annotation and not c_has_annotation:
                    raise TypeError(
                        f"{class_name}.{meth_name}: missing type annotation for '{p.name}'"
                    )

                if p_has_annotation and c_has_annotation:
                    p_ann = StrictABCMeta._normalize_annotation(p.annotation)
                    c_ann = StrictABCMeta._normalize_annotation(c.annotation)

                    if p_ann != c_ann:
                        raise TypeError(
                            f"{class_name}.{meth_name}: type annotation mismatch for "
                            f"'{p.name}' (expected {p_ann}, got {c_ann})"
                        )

        # Extra child positional parameters are allowed only if they are
        # optional, unless they are satisfied by a required parent keyword-only
        # parameter with the same name.
        for c in c_pos[len(p_pos) :]:
            if c.default is inspect.Parameter.empty:
                parent_kw = p_kw.get(c.name)

                if (
                    c.kind == inspect.Parameter.POSITIONAL_OR_KEYWORD
                    and parent_kw is not None
                    and parent_kw.default is inspect.Parameter.empty
                ):
                    continue

                raise TypeError(
                    f"{class_name}.{meth_name}: new required parameter "
                    f"'{c.name}' strengthens precondition and violates LSP"
                )

        # ------------------------------------------------------------------
        # Keyword compatibility.
        # ------------------------------------------------------------------

        parent_keyword_names: set[str] = set()

        for p in p_params:
            if p.kind not in keyword_accessible_kinds:
                continue

            parent_keyword_names.add(p.name)
            c_same = c_by_name_keyword.get(p.name)

            if c_same is not None:
                # If parent parameter could be passed positionally, but child
                # implements it as keyword-only, then positional parent calls
                # are only safe if the child parameter has a default and
                # *args absorbs positional arguments.
                if (
                    p.kind == inspect.Parameter.POSITIONAL_OR_KEYWORD
                    and c_same.kind == inspect.Parameter.KEYWORD_ONLY
                    and c_same.default is inspect.Parameter.empty
                ):
                    raise TypeError(
                        f"{class_name}.{meth_name}: keyword-only implementation of "
                        f"positional-or-keyword parameter '{p.name}' must have "
                        f"a default value"
                    )

                if check_defaults:
                    p_has_default = p.default is not inspect.Parameter.empty
                    c_has_default = c_same.default is not inspect.Parameter.empty

                    if p_has_default and not c_has_default:
                        raise TypeError(
                            f"{class_name}.{meth_name}: removing default value for "
                            f"'{p.name}' strengthens precondition and violates LSP"
                        )

                if check_types:
                    p_has_annotation = p.annotation is not inspect.Parameter.empty
                    c_has_annotation = c_same.annotation is not inspect.Parameter.empty

                    if p_has_annotation and not c_has_annotation:
                        raise TypeError(
                            f"{class_name}.{meth_name}: missing type annotation for '{p.name}'"
                        )

                    if p_has_annotation and c_has_annotation:
                        p_ann = StrictABCMeta._normalize_annotation(p.annotation)
                        c_ann = StrictABCMeta._normalize_annotation(c_same.annotation)

                        if p_ann != c_ann:
                            raise TypeError(
                                f"{class_name}.{meth_name}: type annotation mismatch for "
                                f"'{p.name}' (expected {p_ann}, got {c_ann})"
                            )
            else:
                if not c_has_var_kw:
                    raise TypeError(
                        f"{class_name}.{meth_name}: cannot accept parent keyword "
                        f"parameter '{p.name}' without **kwargs"
                    )

        # Child keyword-only parameters that do not exist in the parent contract
        # must be optional.
        for name, c in c_kw.items():
            if name not in parent_keyword_names and c.default is inspect.Parameter.empty:
                raise TypeError(
                    f"{class_name}.{meth_name}: new required keyword-only parameter "
                    f"'{name}' strengthens precondition and violates LSP"
                )

        # ------------------------------------------------------------------
        # Return type compatibility.
        # ------------------------------------------------------------------

        if check_return_type:
            p_ret: object = sig_parent.return_annotation
            c_ret: object = sig_child.return_annotation

            if p_ret is not inspect.Signature.empty and c_ret is inspect.Signature.empty:
                raise TypeError(f"{class_name}.{meth_name}: missing return type annotation")

            if not StrictABCMeta._is_return_compatible(p_ret, c_ret):
                raise TypeError(
                    f"{class_name}.{meth_name}: return type not covariant "
                    f"(expected {p_ret}, got {c_ret})"
                )


class StrictABC(ABC, metaclass=StrictABCMeta):
    """Convenience base class with sensible default strict options."""

    __strict_options__: ClassVar[StrictOptions] = {
        "check_names": False,
        "check_defaults": True,
        "check_types": False,
        "check_return_type": False,
    }
