"""Metaclass orchestration for runtime LSP-friendly signature validation."""

from __future__ import annotations

import inspect
import warnings
from abc import ABC, ABCMeta
from collections.abc import Callable
from typing import Any, ClassVar, cast

import strict_abc._annotations as _annotations
import strict_abc._descriptors as _descriptors
import strict_abc._signatures as _signatures
import strict_abc._types as _types
from strict_abc._descriptors import DescriptorKind
from strict_abc._errors import LSPViolation
from strict_abc._options import StrictOptions, get_options

__all__ = [
    "DescriptorKind",
    "LSPViolation",
    "StrictABC",
    "StrictABCMeta",
    "StrictOptions",
    "__version__",
    "lsp_exempt",
    "strict",
]

__version__ = "1.0.0"


def lsp_exempt(func: Callable[..., Any]) -> Callable[..., Any]:
    """Mark a method as exempt from LSP signature validation.

    Use this when a subclass intentionally narrows the calling contract
    and the author acknowledges the LSP violation.

    Example:
        >>> class Impl(Base):
        ...     @lsp_exempt
        ...     def process(self, data: dict) -> str:
        ...         return "ok"
    """
    func.__lsp_exempt__ = True  # type: ignore[attr-defined]
    return func


def strict(**opts: Any) -> Callable[[type[Any]], type[Any]]:
    """Inject ``__strict_options__`` without requiring ``StrictABC`` inheritance.

    Example:
        >>> @strict(check_types=True, check_return_type=True)
        ... class Base(ABC, metaclass=StrictABCMeta):
        ...     @abstractmethod
        ...     def run(self) -> None: ...
    """

    def decorator(cls: type[Any]) -> type[Any]:
        cls.__strict_options__ = opts
        return cls

    return decorator


class StrictABCMeta(ABCMeta):
    """Enforce LSP-friendly signatures when concrete classes are created.

    Options are read from ``__strict_options__`` and merged across the MRO.
    Concrete implementations must not strengthen preconditions or remove
    calling forms declared by abstract parent methods.
    """

    def __new__(
        mcls: type[StrictABCMeta],
        name: str,
        bases: tuple[type[Any], ...],
        namespace: dict[str, Any],
        **kwargs: Any,
    ) -> type[Any]:
        """Create a class and validate its abstract method implementations."""
        cls: type[Any] = super().__new__(mcls, name, bases, namespace, **kwargs)

        options = mcls._get_options(cls)
        signature_options = _signatures.SignatureOptions(
            check_names=options.get("check_names", False),
            check_defaults=options.get("check_defaults", True),
            check_types=options.get("check_types", False),
            check_types_contravariant=options.get("check_types_contravariant", False),
            check_return_type=options.get("check_return_type", False),
        )

        parent_abstracts: set[str] = set()
        for base in bases:
            abstract_methods: object = getattr(base, "__abstractmethods__", frozenset())
            if isinstance(abstract_methods, (frozenset, set)):
                parent_abstracts.update(abstract_methods)

        for base in cls.__mro__[1:]:
            for attr_name, base_attr in base.__dict__.items():
                if attr_name in namespace and getattr(base_attr, "__isabstractmethod__", False):
                    parent_abstracts.add(attr_name)

        cls_abstracts_obj: object = getattr(cls, "__abstractmethods__", frozenset())
        cls_abstracts: frozenset[str] = (
            cast("frozenset[str]", cls_abstracts_obj)
            if isinstance(cls_abstracts_obj, frozenset)
            else frozenset()
        )

        violations: list[LSPViolation] = []

        for meth_name in sorted(parent_abstracts):
            if meth_name in cls_abstracts:
                continue

            concrete = mcls._find_concrete_attr(cls, meth_name)
            if concrete is None or getattr(concrete, "__isabstractmethod__", False):
                continue
            if mcls._is_lsp_exempt(concrete):
                continue

            for parent_attr in mcls._find_abstract_attrs(cls, meth_name):
                try:
                    parent_kind = mcls._descriptor_kind(parent_attr)
                    child_kind = mcls._descriptor_kind(concrete)
                except TypeError:
                    continue

                if parent_kind != child_kind:
                    violations.append(
                        LSPViolation(
                            cls.__name__,
                            meth_name,
                            f"descriptor type mismatch (expected {parent_kind}, got {child_kind})",
                        )
                    )
                    continue

                try:
                    parent_func, _ = mcls._unwrap_descriptor(parent_attr)
                    child_func, _ = mcls._unwrap_descriptor(concrete)
                    sig_parent = mcls._signature(parent_func)
                    sig_child = mcls._signature(child_func)
                except (TypeError, ValueError, NameError):
                    continue

                parent_async_kind = mcls._async_kind(parent_func)
                child_async_kind = mcls._async_kind(child_func)
                if parent_async_kind != child_async_kind:
                    violations.append(
                        LSPViolation(
                            cls.__name__,
                            meth_name,
                            f"async/sync mismatch "
                            f"(parent is {parent_async_kind}, "
                            f"child is {child_async_kind})",
                        )
                    )
                    continue

                violations.extend(
                    _signatures.validate_signature(
                        meth_name=meth_name,
                        sig_parent=sig_parent,
                        sig_child=sig_child,
                        parent_descriptor=parent_kind,
                        child_descriptor=child_kind,
                        options=signature_options,
                        class_name=cls.__name__,
                    )
                )

        if violations:
            if options.get("mode", "error") == "warn":
                for violation in violations:
                    warnings.warn(str(violation), stacklevel=2)
            else:
                raise violations[0]

        return cls

    @staticmethod
    def _get_options(cls: type[Any]) -> StrictOptions:
        """Return options merged across the MRO."""
        return get_options(cls)

    @staticmethod
    def _find_concrete_attr(cls: type[Any], name: str) -> object | None:
        """Find the first non-abstract attribute in the MRO."""
        return _descriptors.find_concrete_attr(cls, name)

    @staticmethod
    def _find_abstract_attrs(cls: type[Any], name: str) -> list[object]:
        """Collect unique abstract attributes from base classes."""
        return _descriptors.find_abstract_attrs(cls, name)

    @staticmethod
    def _is_lsp_exempt(attr: object) -> bool:
        """Return whether an attribute is exempt from validation."""
        return _descriptors.is_lsp_exempt(attr)

    @staticmethod
    def _descriptor_kind(attr: object) -> DescriptorKind:
        """Determine the descriptor kind of an attribute."""
        return _descriptors.descriptor_kind(attr)

    @staticmethod
    def _unwrap_descriptor(attr: object) -> tuple[Callable[..., Any], DescriptorKind]:
        """Extract the underlying callable from a descriptor."""
        return _descriptors.unwrap_descriptor(attr, StrictABCMeta._descriptor_kind)

    @staticmethod
    def _async_kind(func: Callable[..., Any]) -> str:
        """Classify a callable as async, async generator, or sync."""
        return _descriptors.async_kind(func)

    @staticmethod
    def _signature(func: Callable[..., Any]) -> inspect.Signature:
        """Obtain an unwrapped signature with annotations evaluated if possible."""
        return _descriptors.signature(func)

    @staticmethod
    def _normalize_annotation(annotation: object) -> object:
        """Normalize a type annotation using safe string evaluation."""
        return _annotations.normalize_annotation(annotation)

    @staticmethod
    def _get_origin(annotation: object) -> object | None:
        """Return an annotation origin."""
        return _annotations.get_origin(annotation)

    @staticmethod
    def _get_args(annotation: object) -> object:
        """Return generic annotation arguments."""
        return _annotations.get_args(annotation)

    @staticmethod
    def _union_args(annotation: object) -> tuple[Any, ...] | None:
        """Return members of a union annotation."""
        return _annotations.union_args(annotation)

    @staticmethod
    def _is_return_compatible(parent_ret: object, child_ret: object) -> bool:
        """Check return type covariance."""
        return _types.is_return_compatible(parent_ret, child_ret)

    @staticmethod
    def _is_param_compatible_contravariant(
        parent_ann: object,
        child_ann: object,
    ) -> bool:
        """Check parameter type contravariance."""
        return _types.is_param_compatible_contravariant(parent_ann, child_ann)

    @staticmethod
    def _validate_signature(
        *,
        meth_name: str,
        sig_parent: inspect.Signature,
        sig_child: inspect.Signature,
        parent_descriptor: DescriptorKind,
        child_descriptor: DescriptorKind,
        check_names: bool,
        check_defaults: bool,
        check_types: bool,
        check_types_contravariant: bool,
        check_return_type: bool,
        class_name: str,
        violations: list[LSPViolation],
    ) -> None:
        """Append signature violations using the legacy private adapter API."""
        violations.extend(
            _signatures.validate_signature(
                meth_name=meth_name,
                sig_parent=sig_parent,
                sig_child=sig_child,
                parent_descriptor=parent_descriptor,
                child_descriptor=child_descriptor,
                options=_signatures.SignatureOptions(
                    check_names=check_names,
                    check_defaults=check_defaults,
                    check_types=check_types,
                    check_types_contravariant=check_types_contravariant,
                    check_return_type=check_return_type,
                ),
                class_name=class_name,
            )
        )


class StrictABC(ABC, metaclass=StrictABCMeta):
    """Convenience base class with default strict options."""

    __strict_options__: ClassVar[StrictOptions] = {
        "check_names": False,
        "check_defaults": True,
        "check_types": False,
        "check_types_contravariant": False,
        "check_return_type": False,
        "mode": "error",
    }
