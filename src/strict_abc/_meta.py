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

import ast
import builtins
import inspect
import types
import typing
import warnings
from abc import ABC, ABCMeta
from collections.abc import Callable, Mapping
from typing import Any, ClassVar, Literal, TypedDict, cast

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

__version__ = "0.3.0"

# Only builtin types may be resolved from string annotations. Never expose
# functions such as ``open``, ``eval``, or ``getattr`` to annotation evaluation.
_SAFE_ANNOTATION_BUILTINS: frozenset[str] = frozenset(
    name
    for name in dir(builtins)
    if isinstance(getattr(builtins, name), type)
)

# ---------------------------------------------------------------------------
# Type aliases
# ---------------------------------------------------------------------------

DescriptorKind = Literal[
    "staticmethod",
    "classmethod",
    "property",
    "instancemethod",
]


# ---------------------------------------------------------------------------
# Options
# ---------------------------------------------------------------------------


class StrictOptions(TypedDict, total=False):
    """Options accepted by ``StrictABCMeta``.

    Attributes:
        check_names: Require equal parameter names between parent and child.
        check_defaults: Forbid removing default values from parameters.
        check_types: Require exact parameter type annotation matching.
        check_types_contravariant: Require contravariant parameter types
            (child may widen the accepted type). Takes precedence over
            ``check_types`` when both are set.
        check_return_type: Require covariant return type annotations.
        mode: Whether violations raise an error or emit a warning.
    """

    check_names: bool
    check_defaults: bool
    check_types: bool
    check_types_contravariant: bool
    check_return_type: bool
    mode: Literal["error", "warn"]


# ---------------------------------------------------------------------------
# Exception
# ---------------------------------------------------------------------------


class LSPViolation(TypeError):
    """Raised when a concrete method violates the LSP calling contract.

    This is a subclass of ``TypeError`` so existing ``except TypeError``
    handlers continue to work.

    Attributes:
        cls_name: Name of the offending class.
        meth_name: Name of the offending method.
        reason: Human-readable description of the violation.
    """

    def __init__(self, cls_name: str, meth_name: str, reason: str) -> None:
        """Initialize the violation.

        Args:
            cls_name: Name of the class that violates the contract.
            meth_name: Name of the method that violates the contract.
            reason: Description of what went wrong.
        """
        self.cls_name = cls_name
        self.meth_name = meth_name
        self.reason = reason
        super().__init__(f"{cls_name}.{meth_name}: {reason}")


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
        resolved: dict[str, object] = {}

        for base in reversed(cls.__mro__):
            raw: object = base.__dict__.get("__strict_options__")
            if isinstance(raw, Mapping):
                resolved.update(cast("Mapping[str, object]", raw))

        return {
            "check_names": bool(resolved.get("check_names", False)),
            "check_defaults": bool(resolved.get("check_defaults", True)),
            "check_types": bool(resolved.get("check_types", False)),
            "check_types_contravariant": bool(
                resolved.get("check_types_contravariant", False)
            ),
            "check_return_type": bool(resolved.get("check_return_type", False)),
            "mode": resolved.get("mode", "error"),  # type: ignore[typeddict-item]
        }

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
        for base in cls.__mro__:
            attr: object = base.__dict__.get(name)
            if attr is not None and not getattr(attr, "__isabstractmethod__", False):
                return attr
        return None

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
        attrs: list[object] = []
        seen: set[int] = set()

        for base in cls.__mro__[1:]:
            attr: object = base.__dict__.get(name)
            if attr is not None and getattr(attr, "__isabstractmethod__", False):
                attr_id = id(attr)
                if attr_id not in seen:
                    attrs.append(attr)
                    seen.add(attr_id)

        return attrs

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
        candidates: list[object] = [attr]

        func = getattr(attr, "__func__", None)
        if func is not None:
            candidates.append(func)

        fget = getattr(attr, "fget", None)
        if fget is not None:
            candidates.append(fget)

        return any(
            bool(getattr(candidate, "__lsp_exempt__", False))
            for candidate in candidates
        )

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
        if isinstance(attr, property):
            return "property"
        if isinstance(attr, staticmethod):
            return "staticmethod"
        if isinstance(attr, classmethod):
            return "classmethod"
        if callable(attr):
            return "instancemethod"
        raise TypeError(f"Unsupported descriptor type: {type(attr)!r}")

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

        raise TypeError(f"Unsupported descriptor type: {type(attr)!r}")

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
        if inspect.iscoroutinefunction(func):
            return "async"
        if inspect.isasyncgenfunction(func):
            return "async generator"
        return "sync"

    @staticmethod
    def _signature(func: Callable[..., Any]) -> inspect.Signature:
        """Obtain the signature of a callable, unwrapping decorators.

        Attempts to evaluate string annotations (PEP 563) when possible.

        Args:
            func: The callable to inspect.

        Returns:
            The ``inspect.Signature`` of the callable.
        """
        func = inspect.unwrap(func)
        try:
            return inspect.signature(func, eval_str=True)
        except Exception:
            return inspect.signature(func)

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
        if annotation is inspect.Parameter.empty:
            return annotation
        if annotation is None:
            return type(None)
        if isinstance(annotation, str):
            # Safely parse and evaluate string annotations
            try:
                # Parse the annotation string
                tree = ast.parse(annotation, mode='eval')

                # Security check: reject dangerous patterns.
                #
                # Underscore attributes are blocked wholesale (``__dict__``,
                # ``__globals__``, ``__class__``, ...), because they can be
                # used to reach the real builtins through otherwise safe
                # objects such as the ``typing`` module. Dunder names are
                # blocked for the same reason.
                dangerous_calls = frozenset(
                    {"exec", "eval", "compile", "open", "getattr", "setattr",
                     "globals", "locals", "vars", "input", "breakpoint"}
                )
                dangerous_attributes = frozenset(
                    {"system", "popen", "exec", "execfile", "func_globals",
                     "f_globals", "gi_frame", "cr_frame"}
                )

                for node in ast.walk(tree):
                    if isinstance(node, ast.Name) and node.id.startswith("__"):
                        return annotation

                    if isinstance(node, ast.Attribute):
                        if node.attr.startswith("_"):
                            return annotation
                        if node.attr in dangerous_attributes:
                            return annotation

                    if isinstance(node, ast.Call):
                        func = node.func
                        if isinstance(func, ast.Name) and func.id in dangerous_calls:
                            return annotation
                        if (
                            isinstance(func, ast.Attribute)
                            and func.attr in dangerous_calls
                        ):
                            return annotation

                # Extract all names used in the annotation
                names: set[str] = set()
                for node in ast.walk(tree):
                    if isinstance(node, ast.Name):
                        names.add(node.id)
                    elif isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
                        # Handle things like typing.Optional
                        names.add(node.value.id)

                # Build a restricted namespace. ``eval`` would otherwise
                # inject the full ``builtins`` module, exposing functions such
                # as ``open`` and ``getattr`` to annotation strings.
                safe_globals: dict[str, Any] = {
                    "__builtins__": {},
                    "typing": typing,
                }

                # Only expose builtin types, never builtin functions.
                for name in names:
                    if name in _SAFE_ANNOTATION_BUILTINS:
                        safe_globals[name] = getattr(builtins, name)

                # Add typing symbols directly if they're used
                typing_symbols = ['Optional', 'Union', 'List', 'Dict', 'Set', 'Tuple',
                                'Callable', 'Any', 'Literal', 'TypeVar', 'Generic',
                                'Protocol', 'Final', 'ClassVar']
                for symbol in typing_symbols:
                    if symbol in names:
                        safe_globals[symbol] = getattr(typing, symbol)

                # Evaluate with safe namespace
                result = eval(compile(tree, '<annotation>', 'eval'), safe_globals)
                if result is None:
                    return type(None)
                return result

            except Exception:
                # If parsing or evaluation fails, return the original string
                return annotation
        return annotation
    
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
        origin = typing.get_origin(annotation)
        if origin is not None:
            return cast("object", origin)
        return cast("object | None", getattr(annotation, "__origin__", None))

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
        args = typing.get_args(annotation)
        if args:
            return cast("object", args)
        return cast("object", getattr(annotation, "__args__", ()))

    @staticmethod
    def _union_args(annotation: object) -> tuple[Any, ...] | None:
        """Return union members for PEP 604 and ``typing.Union`` aliases.

        Args:
            annotation: Type annotation to inspect.

        Returns:
            A tuple of union members, or ``None`` if not a union.
        """
        origin = StrictABCMeta._get_origin(annotation)
        if origin is types.UnionType or origin is typing.Union:
            return cast("tuple[Any, ...]", StrictABCMeta._get_args(annotation))
        return None

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

        def check_variadic_annotation(
            parent_param: inspect.Parameter,
            child_param: inspect.Parameter,
        ) -> None:
            """Validate annotations on matched ``*args`` / ``**kwargs``."""
            if not (check_types or check_types_contravariant):
                return

            p_has_ann = parent_param.annotation is not inspect.Parameter.empty
            c_has_ann = child_param.annotation is not inspect.Parameter.empty

            label = (
                f"*{parent_param.name}"
                if parent_param.kind == inspect.Parameter.VAR_POSITIONAL
                else f"**{parent_param.name}"
            )

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
            check_variadic_annotation(p_var_pos, c_var_pos)
        if p_var_kw is not None and c_var_kw is not None:
            check_variadic_annotation(p_var_kw, c_var_kw)

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
                if not c_has_var_kw:
                    violations.append(
                        LSPViolation(
                            class_name,
                            meth_name,
                            f"cannot accept parent keyword parameter "
                            f"'{p.name}' without **kwargs",
                        ),
                    )
                elif c.default is inspect.Parameter.empty:
                    violations.append(
                        LSPViolation(
                            class_name,
                            meth_name,
                            f"cannot accept parent keyword parameter "
                            f"'{p.name}' because corresponding child "
                            f"parameter has no default",
                        ),
                    )

            # Type annotations.
            if check_types or check_types_contravariant:
                p_has_ann = p.annotation is not inspect.Parameter.empty
                c_has_ann = c.annotation is not inspect.Parameter.empty

                if p_has_ann and not c_has_ann:
                    violations.append(
                        LSPViolation(
                            class_name,
                            meth_name,
                            f"missing type annotation for '{p.name}'",
                        )
                    )
                elif p_has_ann and c_has_ann:
                    p_ann = StrictABCMeta._normalize_annotation(p.annotation)
                    c_ann = StrictABCMeta._normalize_annotation(c.annotation)

                    if check_types_contravariant:
                        if not StrictABCMeta._is_param_compatible_contravariant(
                            p_ann, c_ann
                        ):
                            violations.append(
                                LSPViolation(
                                    class_name,
                                    meth_name,
                                    f"parameter type for '{p.name}' is not "
                                    f"contravariant (parent: {p_ann}, "
                                    f"child: {c_ann})",
                                )
                            )
                    elif p_ann != c_ann:
                        violations.append(
                            LSPViolation(
                                class_name,
                                meth_name,
                                f"type annotation mismatch for '{p.name}' "
                                f"(expected {p_ann}, got {c_ann})",
                            )
                        )

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

                # Guard: если оба параметра POSITIONAL_OR_KEYWORD,
                # defaults/types уже проверены в позиционном цикле,
                # чтобы избежать дублей в списке violations.
                _both_pos_or_kw = (
                    p.kind == inspect.Parameter.POSITIONAL_OR_KEYWORD
                    and c_same.kind == inspect.Parameter.POSITIONAL_OR_KEYWORD
                )

                if not _both_pos_or_kw:
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

                    if check_types or check_types_contravariant:
                        p_has_ann = p.annotation is not inspect.Parameter.empty
                        c_has_ann = c_same.annotation is not inspect.Parameter.empty

                        if p_has_ann and not c_has_ann:
                            violations.append(
                                LSPViolation(
                                    class_name,
                                    meth_name,
                                    f"missing type annotation for '{p.name}'",
                                )
                            )
                        elif p_has_ann and c_has_ann:
                            p_ann = StrictABCMeta._normalize_annotation(p.annotation)
                            c_ann = StrictABCMeta._normalize_annotation(c_same.annotation)

                            if check_types_contravariant:
                                if not StrictABCMeta._is_param_compatible_contravariant(
                                    p_ann, c_ann
                                ):
                                    violations.append(
                                        LSPViolation(
                                            class_name,
                                            meth_name,
                                            f"parameter type for '{p.name}' is not "
                                            f"contravariant (parent: {p_ann}, "
                                            f"child: {c_ann})",
                                        )
                                    )
                            elif p_ann != c_ann:
                                violations.append(
                                    LSPViolation(
                                        class_name,
                                        meth_name,
                                        f"type annotation mismatch for '{p.name}' "
                                        f"(expected {p_ann}, got {c_ann})",
                                    )
                                )
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
                elif (
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