"""Compatibility checks for parameter and return annotations."""

import inspect
from typing import Any, cast

from strict_abc._annotations import get_args, get_origin, normalize_annotation, union_args


def is_return_compatible(parent_ret: object, child_ret: object) -> bool:
    """Check whether a child return type is covariant with the parent."""
    if parent_ret is inspect.Signature.empty:
        return True
    if child_ret is inspect.Signature.empty:
        return False

    parent = normalize_annotation(parent_ret)
    child = normalize_annotation(child_ret)

    if parent is Any or child is Any:
        return True
    if parent == child:
        return True
    if parent is object:
        return True

    child_union = union_args(child)
    if child_union is not None:
        return all(is_return_compatible(parent, member) for member in child_union)

    parent_union = union_args(parent)
    if parent_union is not None:
        return any(is_return_compatible(member, child) for member in parent_union)

    parent_origin = get_origin(parent)
    child_origin = get_origin(child)
    parent_args = cast("tuple[Any, ...]", get_args(parent))
    child_args = cast("tuple[Any, ...]", get_args(child))

    if parent_origin is None and child_origin is None:
        if isinstance(parent, type) and isinstance(child, type):
            try:
                return issubclass(child, parent)
            except TypeError:
                return False
        return False

    if parent_origin is None:
        if isinstance(parent, type) and isinstance(child_origin, type):
            try:
                return issubclass(child_origin, parent)
            except TypeError:
                return False
        return False

    if child_origin is None:
        if not parent_args and isinstance(parent_origin, type) and isinstance(child, type):
            try:
                return issubclass(child, parent_origin)
            except TypeError:
                return False
        return False

    if isinstance(parent_origin, type) and isinstance(child_origin, type):
        try:
            if issubclass(child_origin, parent_origin):
                return (
                    not parent_args
                    or any(arg is Any for arg in parent_args)
                    or parent_args == child_args
                )
        except TypeError:
            return False

    return False


def is_param_compatible_contravariant(parent_ann: object, child_ann: object) -> bool:
    """Check whether a child parameter accepts a valid supertype of the parent."""
    if parent_ann is inspect.Parameter.empty:
        return True
    if child_ann is inspect.Parameter.empty:
        return False

    parent = normalize_annotation(parent_ann)
    child = normalize_annotation(child_ann)

    if child is Any or child is object:
        return True
    if parent is Any:
        return True
    if parent == child:
        return True

    parent_union = union_args(parent)
    if parent_union is not None:
        return all(is_param_compatible_contravariant(member, child) for member in parent_union)

    child_union = union_args(child)
    if child_union is not None:
        return any(is_param_compatible_contravariant(parent, member) for member in child_union)

    parent_origin = get_origin(parent)
    child_origin = get_origin(child)

    if parent_origin is None and child_origin is None:
        if isinstance(parent, type) and isinstance(child, type):
            try:
                return issubclass(parent, child)
            except TypeError:
                return False
        return False

    if parent_origin is None:
        if (
            child_origin is not None
            and not get_args(child)
            and isinstance(parent, type)
            and isinstance(child_origin, type)
        ):
            try:
                return issubclass(parent, child_origin)
            except TypeError:
                return False
        return False

    if child_origin is None:
        if isinstance(child, type) and isinstance(parent_origin, type):
            try:
                return issubclass(parent_origin, child)
            except TypeError:
                return False
        return False

    parent_args = cast("tuple[Any, ...]", get_args(parent))
    child_args = cast("tuple[Any, ...]", get_args(child))

    if isinstance(parent_origin, type) and isinstance(child_origin, type):
        try:
            if issubclass(parent_origin, child_origin):
                return not child_args or parent_args == child_args
        except TypeError:
            return False

    return False
