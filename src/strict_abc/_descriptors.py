"""Attribute discovery and callable introspection helpers."""

import inspect
from collections.abc import Callable
from typing import Any, Literal

DescriptorKind = Literal[
    "staticmethod",
    "classmethod",
    "property",
    "instancemethod",
]


def find_concrete_attr(cls: type[Any], name: str) -> object | None:
    """Find the first non-abstract attribute with the given name in the MRO."""
    for base in cls.__mro__:
        attr: object = base.__dict__.get(name)
        if attr is not None and not getattr(attr, "__isabstractmethod__", False):
            return attr
    return None


def find_abstract_attrs(cls: type[Any], name: str) -> list[object]:
    """Collect unique abstract attributes with the given name from base classes."""
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


def is_lsp_exempt(attr: object) -> bool:
    """Return whether an attribute or its underlying callable is exempt."""
    candidates: list[object] = [attr]

    func = getattr(attr, "__func__", None)
    if func is not None:
        candidates.append(func)

    fget = getattr(attr, "fget", None)
    if fget is not None:
        candidates.append(fget)

    return any(bool(getattr(candidate, "__lsp_exempt__", False)) for candidate in candidates)


def descriptor_kind(attr: object) -> DescriptorKind:
    """Determine the descriptor kind of an attribute."""
    if isinstance(attr, property):
        return "property"
    if isinstance(attr, staticmethod):
        return "staticmethod"
    if isinstance(attr, classmethod):
        return "classmethod"
    if callable(attr):
        return "instancemethod"
    raise TypeError(f"Unsupported descriptor type: {type(attr)!r}")


def unwrap_descriptor(
    attr: object,
    kind_resolver: Callable[[object], DescriptorKind] = descriptor_kind,
) -> tuple[Callable[..., Any], DescriptorKind]:
    """Extract the underlying callable from a descriptor."""
    kind = kind_resolver(attr)

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


def async_kind(func: Callable[..., Any]) -> str:
    """Classify a callable as ``async``, ``async generator``, or ``sync``."""
    if inspect.iscoroutinefunction(func):
        return "async"
    if inspect.isasyncgenfunction(func):
        return "async generator"
    return "sync"


def signature(func: Callable[..., Any]) -> inspect.Signature:
    """Obtain an unwrapped signature, evaluating annotations when possible."""
    func = inspect.unwrap(func)
    try:
        return inspect.signature(func, eval_str=True)
    except Exception:
        return inspect.signature(func)
