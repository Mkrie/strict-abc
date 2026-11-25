"""Runtime LSP-friendly signature validation for abstract base classes.

This module provides ``StrictABCMeta`` and ``StrictABC``, which enforce
that concrete implementations of abstract methods preserve the calling
contract declared by the parent class.

Example:
    >>> from abc import abstractmethod
    >>> from strict_abc import StrictABC
    >>>
    >>> class BaseService(StrictABC):
    ...     @abstractmethod
    ...     def process(self, data: dict, cache: bool = True) -> str: ...
    ...
    >>> class ValidService(BaseService):
    ...     def process(self, data: dict, cache: bool = True) -> str:
    ...         return "ok"
"""

from __future__ import annotations

import inspect
import warnings
from abc import ABC, ABCMeta
from collections.abc import Callable
from typing import Any, ClassVar, cast

from strict_abc._annotations import (
    get_args as _get_args,
)
from strict_abc._annotations import (
    get_origin as _get_origin,
)
from strict_abc._annotations import (
    normalize_annotation as _normalize_annotation,
)
from strict_abc._annotations import (
    union_args as _union_args,
)
from strict_abc._descriptors import (
    DescriptorKind,
)
from strict_abc._descriptors import (
    async_kind as _async_kind,
)
from strict_abc._descriptors import (
    descriptor_kind as _descriptor_kind,
)
from strict_abc._descriptors import (
    find_abstract_attrs as _find_abstract_attrs,
)
from strict_abc._descriptors import (
    find_concrete_attr as _find_concrete_attr,
)
from strict_abc._descriptors import (
    is_lsp_exempt as _is_lsp_exempt,
)
from strict_abc._descriptors import (
    signature as _signature,
)
from strict_abc._descriptors import (
    unwrap_descriptor as _unwrap_descriptor,
)
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

__version__ = "0.4.0"

# ---------------------------------------------------------------------------
# Decorators
# ---------------------------------------------------------------------------


def lsp_exempt(func: Callable[..., Any]) -> Callable[..., Any]:
    """Mark a method as exempt from LSP signature validation.

    Use this when a subclass intentionally narrows the calling contract
    and the author acknowledges the LSP violation.

    Args:
        func: The method to exempt.

    Returns:
        The same function with an ``__lsp_exempt__`` attribute set.

    Example:
        >>> class Impl(Base):
        ...     @lsp_exempt
        ...     def process(self, data: dict) -> str:
        ...         return "ok"
    """
    func.__lsp_exempt__ = True  # type: ignore[attr-defined]
    return func


def strict(**opts: Any) -> Callable[[type[Any]], type[Any]]:
    """Class decorator that injects ``__strict_options__`` without inheritance.

    This is an alternative to subclassing ``StrictABC`` for cases where
    you already have a different base class or metaclass hierarchy.

    Args:
        **opts: Keyword arguments matching ``StrictOptions`` fields.

    Returns:
        A class decorator that sets ``__strict_options__``.

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


# ---------------------------------------------------------------------------
# Metaclass
# ---------------------------------------------------------------------------


class StrictABCMeta(ABCMeta):
    """Metaclass that enforces LSP-friendly signatures at class creation time.

    When a class using this metaclass provides a concrete implementation
    of an abstract method, the metaclass validates that the implementation
    does not strengthen preconditions or remove accepted calling forms.

    Options are read from ``__strict_options__`` and merged across the MRO.

    Supported options:
        * ``check_names``: Require equal parameter names.
        * ``check_defaults``: Forbid removing default values.
        * ``check_types``: Require exact parameter type annotations.
        * ``check_types_contravariant``: Require contravariant parameter types.
        * ``check_return_type``: Require covariant return type annotations.
        * ``mode``: ``"error"`` (default) or ``"warn"``.
    """

    def __new__(
        mcls: type[StrictABCMeta],
        name: str,
        bases: tuple[type[Any], ...],
        namespace: dict[str, Any],
        **kwargs: Any,
    ) -> type[Any]:
        """Create a new class and validate abstract method implementations.

        Args:
            mcls: The metaclass itself.
            name: Name of the class being created.
            bases: Base classes.
            namespace: Class body namespace.
            **kwargs: Additional keyword arguments passed to ``type.__new__``.

        Returns:
            The newly created class.

        Raises:
            LSPViolation: If a concrete method violates the parent contract
                and ``mode`` is ``"error"``.
        """
        cls: type[Any] = super().__new__(mcls, name, bases, namespace, **kwargs)

        options: StrictOptions = mcls._get_options(cls)
        mode: str = options.get("mode", "error")

        check_names: bool = bool(options.get("check_names", False))
        check_defaults: bool = bool(options.get("check_defaults", True))
        check_types: bool = bool(options.get("check_types", False))
        check_types_contravariant: bool = bool(
            options.get("check_types_contravariant", False)
        )
        check_return_type: bool = bool(options.get("check_return_type", False))

        parent_abstracts: set[str] = set()
        for base in bases:
            abstract_methods: object = getattr(base, "__abstractmethods__", frozenset())
            if isinstance(abstract_methods, (frozenset, set)):
                parent_abstracts.update(abstract_methods)

        # Direct bases only expose methods that are still abstract. A class can
        # also override an implementation that already satisfied an abstract
        # contract higher in the MRO, so validate names redefined in this class
        # body against every abstract declaration in the MRO.
        for base in cls.__mro__[1:]:
            for attr_name, base_attr in base.__dict__.items():
                if attr_name in namespace and getattr(
                    base_attr, "__isabstractmethod__", False
                ):
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
            if concrete is None:
                continue
            if getattr(concrete, "__isabstractmethod__", False):
                continue
            if mcls._is_lsp_exempt(concrete):
                continue

            abstract_attrs = mcls._find_abstract_attrs(cls, meth_name)

            for parent_attr in abstract_attrs:
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
                            f"descriptor type mismatch "
                            f"(expected {parent_kind}, got {child_kind})",
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

                # Async/sync mismatch check.
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

                mcls._validate_signature(
                    meth_name=meth_name,
                    sig_parent=sig_parent,
                    sig_child=sig_child,
                    parent_descriptor=parent_kind,
                    child_descriptor=child_kind,
                    check_names=check_names,
                    check_defaults=check_defaults,
                    check_types=check_types,
                    check_types_contravariant=check_types_contravariant,
                    check_return_type=check_return_type,
                    class_name=cls.__name__,
                    violations=violations,
                )

        if violations:
            if mode == "warn":
                for v in violations:
                    warnings.warn(str(v), stacklevel=2)
            else:
                raise violations[0]

        return cls

    # ------------------------------------------------------------------
    # Options resolution
    # ------------------------------------------------------------------

    @staticmethod
    def _get_options(cls: type[Any]) -> StrictOptions:
        """Merge ``__strict_options__`` across the MRO.

        Options defined in subclasses override those in parent classes.
        The merge is shallow (key-by-key), so a subclass only needs to
        specify the keys it wants to change.

        Args:
            cls: The class whose options should be resolved.

        Returns:
            A fully-populated ``StrictOptions`` dict with defaults applied.
        """
        return get_options(cls)

    # ------------------------------------------------------------------
    # Attribute discovery
    # ------------------------------------------------------------------

    @staticmethod
    def _find_concrete_attr(cls: type[Any], name: str) -> object | None:
        """Find the first non-abstract attribute with the given name in the MRO.

        Args:
            cls: The class to search.
            name: Attribute name.

        Returns:
            The concrete attribute, or ``None`` if not found.
        """
        return _find_concrete_attr(cls, name)

    @staticmethod
    def _find_abstract_attrs(cls: type[Any], name: str) -> list[object]:
        """Collect all abstract attributes with the given name from base classes.

        Uses ``id()`` to deduplicate in diamond-inheritance scenarios.

        Args:
            cls: The class whose bases should be searched.
            name: Attribute name.

        Returns:
            A list of unique abstract attribute objects.
        """
        return _find_abstract_attrs(cls, name)

    @staticmethod
    def _is_lsp_exempt(attr: object) -> bool:
        """Return whether an attribute is marked with ``@lsp_exempt``.

        The marker may live on the function itself, on the descriptor
        (``staticmethod`` / ``classmethod``), or on a property getter,
        depending on decorator order.

        Args:
            attr: A class-level attribute.

        Returns:
            ``True`` if any underlying callable is exempt.
        """
        return _is_lsp_exempt(attr)

    # ------------------------------------------------------------------
    # Descriptor introspection
    # ------------------------------------------------------------------

    @staticmethod
    def _descriptor_kind(attr: object) -> DescriptorKind:
        """Determine the descriptor kind of an attribute.

        Args:
            attr: A class-level attribute (function, property, etc.).

        Returns:
            One of ``"staticmethod"``, ``"classmethod"``, ``"property"``,
            or ``"instancemethod"``.

        Raises:
            TypeError: If the attribute is not a recognized descriptor type.
        """
        return _descriptor_kind(attr)

    @staticmethod
    def _unwrap_descriptor(attr: object) -> tuple[Callable[..., Any], DescriptorKind]:
        """Extract the underlying callable from a descriptor.

        Args:
            attr: A class-level attribute.

        Returns:
            A tuple of ``(callable, descriptor_kind)``.

        Raises:
            TypeError: If the attribute cannot be unwrapped.
        """
        return _unwrap_descriptor(attr, StrictABCMeta._descriptor_kind)

    # ------------------------------------------------------------------
    # Signature helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _async_kind(func: Callable[..., Any]) -> str:
        """Classify a callable as ``"async"``, ``"async generator"``, or ``"sync"``.

        Regular generator functions are treated as ``"sync"`` so that an
        abstract method declared with ``def`` may still be implemented as a
        generator (a common pattern for ``Iterator`` return types).

        Args:
            func: The callable to classify.

        Returns:
            A human-readable kind used in violation messages.
        """
        return _async_kind(func)

    @staticmethod
    def _signature(func: Callable[..., Any]) -> inspect.Signature:
        """Obtain the signature of a callable, unwrapping decorators.

        Attempts to evaluate string annotations (PEP 563) when possible.

        Args:
            func: The callable to inspect.

        Returns:
            The ``inspect.Signature`` of the callable.
        """
        return _signature(func)

    @staticmethod
    def _normalize_annotation(annotation: object) -> object:
        """Normalize a type annotation for comparison.

        Handles ``None`` -> ``type(None)`` and safely resolves string
        annotations produced by ``from __future__ import annotations``.

        Uses AST parsing with security checks to prevent code injection
        through malicious annotation strings.

        Args:
            annotation: A raw annotation object.

        Returns:
            The normalized annotation.
        """
        return _normalize_annotation(annotation)
    
    @staticmethod
    def _get_origin(annotation: object) -> object | None:
        """Return the annotation origin, if present.

        Uses :func:`typing.get_origin` first and falls back to the
        ``__origin__`` attribute for non-standard generic objects.

        Args:
            annotation: Type annotation to inspect.

        Returns:
            The annotation origin or ``None`` if absent.
        """
        return _get_origin(annotation)

    @staticmethod
    def _get_args(annotation: object) -> object:
        """Return generic annotation arguments.

        Uses :func:`typing.get_args` first and falls back to the
        ``__args__`` attribute for non-standard generic objects.

        Args:
            annotation: Type annotation to inspect.

        Returns:
            Generic arguments, or an empty tuple if absent.
        """
        return _get_args(annotation)

    @staticmethod
    def _union_args(annotation: object) -> tuple[Any, ...] | None:
        """Return union members for PEP 604 and ``typing.Union`` aliases.

        Args:
            annotation: Type annotation to inspect.

        Returns:
            A tuple of union members, or ``None`` if not a union.
        """
        return _union_args(annotation)

    # ------------------------------------------------------------------
    # Type compatibility
    # ------------------------------------------------------------------

    @staticmethod
    def _is_return_compatible(parent_ret: object, child_ret: object) -> bool:
        """Check whether a child return type is covariant with the parent.

        Args:
            parent_ret: The parent method's return annotation.
            child_ret: The child method's return annotation.

        Returns:
            ``True`` if the child return type is compatible (covariant).
        """
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

        if p is object:
            return True

        c_union = StrictABCMeta._union_args(c)
        if c_union is not None:
            return all(
                StrictABCMeta._is_return_compatible(p, member)
                for member in c_union
            )

        p_union = StrictABCMeta._union_args(p)
        if p_union is not None:
            return any(
                StrictABCMeta._is_return_compatible(member, c)
                for member in p_union
            )

        p_origin = StrictABCMeta._get_origin(p)
        c_origin = StrictABCMeta._get_origin(c)
        p_args = cast("tuple[Any, ...]", StrictABCMeta._get_args(p))
        c_args = cast("tuple[Any, ...]", StrictABCMeta._get_args(c))

        # Generic aliases must be compared through origin/args before the
        # plain issubclass() branch. On Python 3.10 parameterized generics
        # may enter the isinstance(..., type) path, but issubclass() on them
        # is not a reliable LSP check.
        if p_origin is None and c_origin is None:
            if isinstance(p, type) and isinstance(c, type):
                try:
                    return issubclass(c, p)
                except TypeError:
                    return False
            return False

        # A bare parent (e.g. ``list``) accepts any parameterized subtype
        # (e.g. ``list[int]``).
        if p_origin is None:
            if isinstance(p, type) and isinstance(c_origin, type):
                try:
                    return issubclass(c_origin, p)
                except TypeError:
                    return False
            return False

        # A bare parent alias (e.g. ``typing.List`` / ``typing.Sequence``)
        # has no generic constraints, so a bare subclass is covariant.
        if c_origin is None:
            if not p_args and isinstance(p_origin, type) and isinstance(c, type):
                try:
                    return issubclass(c, p_origin)
                except TypeError:
                    return False
            return False

        if isinstance(p_origin, type) and isinstance(c_origin, type):
            try:
                if issubclass(c_origin, p_origin):
                    return (
                        not p_args
                        or any(arg is Any for arg in p_args)
                        or p_args == c_args
                    )
            except TypeError:
                return False

        return False

    @staticmethod
    def _is_param_compatible_contravariant(
        parent_ann: object,
        child_ann: object,
    ) -> bool:
        """Check whether a child parameter type is contravariant with the parent.

        Under contravariance the child may *widen* the accepted type:
        ``parent: int`` → ``child: int | str`` is valid.

        Args:
            parent_ann: The parent parameter annotation.
            child_ann: The child parameter annotation.

        Returns:
            ``True`` if the child annotation is a valid supertype.
        """
        if parent_ann is inspect.Parameter.empty:
            return True
        if child_ann is inspect.Parameter.empty:
            return False

        p = StrictABCMeta._normalize_annotation(parent_ann)
        c = StrictABCMeta._normalize_annotation(child_ann)

        if c is Any or c is object:
            return True
        if p is Any:
            return True
        if p == c:
            return True

        p_union = StrictABCMeta._union_args(p)
        if p_union is not None:
            return all(
                StrictABCMeta._is_param_compatible_contravariant(member, c)
                for member in p_union
            )

        c_union = StrictABCMeta._union_args(c)
        if c_union is not None:
            return any(
                StrictABCMeta._is_param_compatible_contravariant(p, member)
                for member in c_union
            )

        p_origin = StrictABCMeta._get_origin(p)
        c_origin = StrictABCMeta._get_origin(c)

        if p_origin is None and c_origin is None:
            if isinstance(p, type) and isinstance(c, type):
                try:
                    return issubclass(p, c)
                except TypeError:
                    return False
            return False

        if p_origin is None:
            # A bare typing alias with no arguments (e.g. ``typing.Sequence``)
            # is a valid supertype of a bare class.
            if (
                c_origin is not None
                and not StrictABCMeta._get_args(c)
                and isinstance(p, type)
                and isinstance(c_origin, type)
            ):
                try:
                    return issubclass(p, c_origin)
                except TypeError:
                    return False
            return False

        # Parent is parameterized; the child may widen it to a supertype.
        if c_origin is None:
            if isinstance(c, type) and isinstance(p_origin, type):
                try:
                    return issubclass(p_origin, c)
                except TypeError:
                    return False
            return False

        p_args = cast("tuple[Any, ...]", StrictABCMeta._get_args(p))
        c_args = cast("tuple[Any, ...]", StrictABCMeta._get_args(c))

        if isinstance(p_origin, type) and isinstance(c_origin, type):
            try:
                if issubclass(p_origin, c_origin):
                    return not c_args or p_args == c_args
            except TypeError:
                return False

        return False

    # ------------------------------------------------------------------
    # Main validation
    # ------------------------------------------------------------------

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
        """Validate a child signature against the parent contract.

        Appends any violations to the ``violations`` list rather than
        raising immediately, so that multiple issues can be reported.

        Args:
            meth_name: Name of the method being validated.
            sig_parent: Signature of the abstract (parent) method.
            sig_child: Signature of the concrete (child) method.
            parent_descriptor: Descriptor kind of the parent attribute.
            child_descriptor: Descriptor kind of the child attribute.
            check_names: Whether to enforce parameter name equality.
            check_defaults: Whether to forbid removing defaults.
            check_types: Whether to enforce exact type matching.
            check_types_contravariant: Whether to enforce contravariant types.
            check_return_type: Whether to enforce covariant return types.
            class_name: Name of the child class (for error messages).
            violations: Mutable list to append violations to.
        """
        p_params: list[inspect.Parameter] = list(sig_parent.parameters.values())
        c_params: list[inspect.Parameter] = list(sig_child.parameters.values())

        # Strip implicit first parameter (self / cls) for non-static methods.
        if parent_descriptor != "staticmethod" and p_params:
            p_params = p_params[1:]
        if child_descriptor != "staticmethod" and c_params:
            c_params = c_params[1:]

        # Detect variadic parameters.
        p_var_pos = next(
            (p for p in p_params if p.kind == inspect.Parameter.VAR_POSITIONAL),
            None,
        )
        p_var_kw = next(
            (p for p in p_params if p.kind == inspect.Parameter.VAR_KEYWORD),
            None,
        )
        c_var_pos = next(
            (c for c in c_params if c.kind == inspect.Parameter.VAR_POSITIONAL),
            None,
        )
        c_var_kw = next(
            (c for c in c_params if c.kind == inspect.Parameter.VAR_KEYWORD),
            None,
        )

        p_has_var_pos = p_var_pos is not None
        p_has_var_kw = p_var_kw is not None
        c_has_var_pos = c_var_pos is not None
        c_has_var_kw = c_var_kw is not None

        def check_annotation(
            parent_param: inspect.Parameter,
            child_param: inspect.Parameter,
            label: str,
        ) -> None:
            if not (check_types or check_types_contravariant):
                return

            p_has_ann = parent_param.annotation is not inspect.Parameter.empty
            c_has_ann = child_param.annotation is not inspect.Parameter.empty

            if p_has_ann and not c_has_ann:
                violations.append(
                    LSPViolation(
                        class_name,
                        meth_name,
                        f"missing type annotation for '{label}'",
                    )
                )
                return

            if not (p_has_ann and c_has_ann):
                return

            p_ann = StrictABCMeta._normalize_annotation(parent_param.annotation)
            c_ann = StrictABCMeta._normalize_annotation(child_param.annotation)

            if check_types_contravariant:
                if not StrictABCMeta._is_param_compatible_contravariant(
                    p_ann, c_ann
                ):
                    violations.append(
                        LSPViolation(
                            class_name,
                            meth_name,
                            f"parameter type for '{label}' is not "
                            f"contravariant (parent: {p_ann}, child: {c_ann})",
                        )
                    )
            elif p_ann != c_ann:
                violations.append(
                    LSPViolation(
                        class_name,
                        meth_name,
                        f"type annotation mismatch for '{label}' "
                        f"(expected {p_ann}, got {c_ann})",
                    )
                )

        # --- Variadic removal -------------------------------------------

        if p_has_var_pos and not c_has_var_pos:
            violations.append(
                LSPViolation(
                    class_name,
                    meth_name,
                    "removed *args from parent signature (violates LSP)",
                )
            )

        if p_has_var_kw and not c_has_var_kw:
            violations.append(
                LSPViolation(
                    class_name,
                    meth_name,
                    "removed **kwargs from parent signature (violates LSP)",
                )
            )

        if p_var_pos is not None and c_var_pos is not None:
            check_annotation(p_var_pos, c_var_pos, f"*{p_var_pos.name}")
        if p_var_kw is not None and c_var_kw is not None:
            check_annotation(p_var_kw, c_var_kw, f"**{p_var_kw.name}")

        # --- Categorize parameters --------------------------------------

        positional_kinds = (
            inspect.Parameter.POSITIONAL_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
        )
        keyword_accessible_kinds = (
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            inspect.Parameter.KEYWORD_ONLY,
        )

        p_pos = [p for p in p_params if p.kind in positional_kinds]
        c_pos = [c for c in c_params if c.kind in positional_kinds]

        p_kw: dict[str, inspect.Parameter] = {
            p.name: p for p in p_params if p.kind == inspect.Parameter.KEYWORD_ONLY
        }
        c_kw: dict[str, inspect.Parameter] = {
            c.name: c for c in c_params if c.kind == inspect.Parameter.KEYWORD_ONLY
        }

        c_by_name_keyword: dict[str, inspect.Parameter] = {
            c.name: c for c in c_params if c.kind in keyword_accessible_kinds
        }
        c_param_names = {c.name for c in c_params}
        compared_positional_pairs: set[tuple[int, int]] = set()
        stripped_parent_signature = inspect.Signature(p_params)

        def has_keyword_collision(position: int, child_name: str) -> bool:
            if not any(
                p.name == child_name and p.kind in keyword_accessible_kinds
                for p in p_params
            ):
                return False
            positional_limit = len(p_pos)
            if p_has_var_pos:
                positional_limit = max(positional_limit, position + 1)
            for positional_count in range(position + 1, positional_limit + 1):
                args = (None,) * positional_count
                kwargs = {child_name: None}
                positional_names = {
                    p.name
                    for p in p_pos[:positional_count]
                    if p.kind == inspect.Parameter.POSITIONAL_OR_KEYWORD
                }
                for p in p_params:
                    if (
                        p.kind in keyword_accessible_kinds
                        and p.default is inspect.Parameter.empty
                        and p.name not in positional_names
                        and p.name not in kwargs
                    ):
                        kwargs[p.name] = None
                try:
                    stripped_parent_signature.bind(*args, **kwargs)
                except TypeError:
                    continue
                return True
            return False

        reported_name_mismatches: set[str] = set()

        # --- Positional compatibility -----------------------------------

        if len(c_pos) < len(p_pos) and not c_has_var_pos:
            violations.append(
                LSPViolation(
                    class_name,
                    meth_name,
                    "cannot accept parent positional parameters without *args",
                )
            )

        allowed_kind_expansions = {
            (
                inspect.Parameter.POSITIONAL_ONLY,
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
            ),
        }

        for p, c in zip(p_pos, c_pos, strict=False):
            compared_positional_pairs.add((id(p), id(c)))

            # Default removal.
            if check_defaults:
                p_has_default = p.default is not inspect.Parameter.empty
                c_has_default = c.default is not inspect.Parameter.empty

                if p_has_default and not c_has_default:
                    violations.append(
                        LSPViolation(
                            class_name,
                            meth_name,
                            f"removing default value for '{p.name}' "
                            f"strengthens precondition and violates LSP",
                        )
                    )

            # Kind transition.
            if p.kind != c.kind and (p.kind, c.kind) not in allowed_kind_expansions:
                keyword_is_preserved = (
                    p.kind == inspect.Parameter.POSITIONAL_OR_KEYWORD
                    and c.kind == inspect.Parameter.POSITIONAL_ONLY
                    and (p.name != c.name or c.default is not inspect.Parameter.empty)
                    and (c_has_var_kw or p.name in c_by_name_keyword)
                )
                if not keyword_is_preserved:
                    violations.append(
                        LSPViolation(
                            class_name,
                            meth_name,
                            f"parameter '{p.name}' kind transition "
                            f"{p.kind.name} -> {c.kind.name} restricts call syntax "
                            f"and violates LSP",
                        )
                    )

            # Name check (explicit option).
            if check_names and p.name != c.name:
                reported_name_mismatches.add(p.name)
                violations.append(
                    LSPViolation(
                        class_name,
                        meth_name,
                        f"parameter name mismatch "
                        f"(expected '{p.name}', got '{c.name}')",
                    )
                )

            # Keyword-call contract for positional-or-keyword parameters.
            if (
                p.kind == inspect.Parameter.POSITIONAL_OR_KEYWORD
                and p.name != c.name
            ):
                if c.default is inspect.Parameter.empty:
                    violations.append(
                        LSPViolation(
                            class_name,
                            meth_name,
                            f"cannot accept parent keyword parameter "
                            f"'{p.name}' because corresponding child "
                            f"parameter has no default",
                        ),
                    )
                if p.name not in c_by_name_keyword and not c_has_var_kw:
                    violations.append(
                        LSPViolation(
                            class_name,
                            meth_name,
                            f"cannot accept parent keyword parameter "
                            f"'{p.name}' without **kwargs",
                        ),
                    )

            # Type annotations.
            check_annotation(p, c, p.name)

        for position, c in enumerate(c_pos):
            parent_positional = p_pos[position] if position < len(p_pos) else None
            if (
                (parent_positional is None or parent_positional.name != c.name)
                and c.kind == inspect.Parameter.POSITIONAL_OR_KEYWORD
                and has_keyword_collision(position, c.name)
            ):
                violations.append(
                    LSPViolation(
                        class_name,
                        meth_name,
                        f"parameter '{c.name}' can receive multiple values "
                        f"for a valid parent call",
                    )
                )

        if c_var_pos is not None:
            for p in p_pos[len(c_pos):]:
                check_annotation(p, c_var_pos, p.name)

        # Extra child positional parameters must be optional.
        for c in c_pos[len(p_pos):]:
            if c.default is inspect.Parameter.empty:
                parent_kw = p_kw.get(c.name)
                if (
                    c.kind == inspect.Parameter.POSITIONAL_OR_KEYWORD
                    and parent_kw is not None
                    and parent_kw.default is inspect.Parameter.empty
                ):
                    continue
                violations.append(
                    LSPViolation(
                        class_name,
                        meth_name,
                        f"new required parameter '{c.name}' strengthens "
                        f"precondition and violates LSP",
                    )
                )

        # --- Keyword compatibility --------------------------------------

        parent_keyword_names: set[str] = set()

        for p in p_params:
            if p.kind not in keyword_accessible_kinds:
                continue

            parent_keyword_names.add(p.name)
            c_same = c_by_name_keyword.get(p.name)

            if c_same is not None:
                # Positional-or-keyword → keyword-only transition.
                if (
                    p.kind == inspect.Parameter.POSITIONAL_OR_KEYWORD
                    and c_same.kind == inspect.Parameter.KEYWORD_ONLY
                    and c_same.default is inspect.Parameter.empty
                ):
                    violations.append(
                        LSPViolation(
                            class_name,
                            meth_name,
                            f"keyword-only implementation of "
                            f"positional-or-keyword parameter '{p.name}' "
                            f"must have a default value or *args",
                        )
                    )

                already_checked = (id(p), id(c_same)) in compared_positional_pairs

                if not already_checked:
                    if check_defaults:
                        p_has_default = p.default is not inspect.Parameter.empty
                        c_has_default = c_same.default is not inspect.Parameter.empty

                        if p_has_default and not c_has_default:
                            violations.append(
                                LSPViolation(
                                    class_name,
                                    meth_name,
                                    f"removing default value for '{p.name}' "
                                    f"strengthens precondition and violates LSP",
                                )
                            )

                    check_annotation(p, c_same, p.name)
            else:
                if not c_has_var_kw:
                    violations.append(
                        LSPViolation(
                            class_name,
                            meth_name,
                            f"cannot accept parent keyword parameter "
                            f"'{p.name}' without **kwargs",
                        )
                    )
                elif c_var_kw is not None:
                    check_annotation(p, c_var_kw, p.name)
                    if (
                        check_names
                        and p.name not in c_param_names
                        and p.name not in reported_name_mismatches
                    ):
                        violations.append(
                            LSPViolation(
                                class_name,
                                meth_name,
                                f"parameter name mismatch "
                                f"(expected '{p.name}', got '**kwargs')",
                            )
                        )

        # New keyword-only parameters must be optional.
        for kw_name, c in c_kw.items():
            if kw_name not in parent_keyword_names and c.default is inspect.Parameter.empty:
                violations.append(
                    LSPViolation(
                        class_name,
                        meth_name,
                        f"new required keyword-only parameter '{kw_name}' "
                        f"strengthens precondition and violates LSP",
                    )
                )

        # --- Return type covariance -------------------------------------

        if check_return_type:
            p_ret: object = sig_parent.return_annotation
            c_ret: object = sig_child.return_annotation

            if (
                p_ret is not inspect.Signature.empty
                and c_ret is inspect.Signature.empty
            ):
                violations.append(
                    LSPViolation(
                        class_name,
                        meth_name,
                        "missing return type annotation",
                    )
                )
            elif not StrictABCMeta._is_return_compatible(p_ret, c_ret):
                violations.append(
                    LSPViolation(
                        class_name,
                        meth_name,
                        f"return type not covariant "
                        f"(expected {p_ret}, got {c_ret})",
                    )
                )


# ---------------------------------------------------------------------------
# Convenience base class
# ---------------------------------------------------------------------------


class StrictABC(ABC, metaclass=StrictABCMeta):
    """Convenience base class with sensible default strict options.

    Subclass this instead of ``ABC`` to get automatic LSP signature
    validation for all abstract method implementations.

    Example:
        >>> class MyService(StrictABC):
        ...     @abstractmethod
        ...     def run(self, timeout: int = 30) -> None: ...
    """

    __strict_options__: ClassVar[StrictOptions] = {
        "check_names": False,
        "check_defaults": True,
        "check_types": False,
        "check_types_contravariant": False,
        "check_return_type": False,
        "mode": "error",
    }