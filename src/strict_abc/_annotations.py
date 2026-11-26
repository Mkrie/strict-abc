"""Safe normalization and inspection of type annotations."""

import ast
import builtins
import inspect
import types
import typing
from typing import Any, cast

_SAFE_ANNOTATION_BUILTINS: frozenset[str] = frozenset(
    name for name in dir(builtins) if isinstance(getattr(builtins, name), type)
)
_DANGEROUS_CALLS = frozenset(
    {
        "exec",
        "eval",
        "compile",
        "open",
        "getattr",
        "setattr",
        "globals",
        "locals",
        "vars",
        "input",
        "breakpoint",
    }
)
_DANGEROUS_ATTRIBUTES = frozenset(
    {
        "system",
        "popen",
        "exec",
        "execfile",
        "func_globals",
        "f_globals",
        "gi_frame",
        "cr_frame",
    }
)
_TYPING_SYMBOLS = (
    "Optional",
    "Union",
    "List",
    "Dict",
    "Set",
    "Tuple",
    "Callable",
    "Any",
    "Literal",
    "TypeVar",
    "Generic",
    "Protocol",
    "Final",
    "ClassVar",
)


def normalize_annotation(annotation: object) -> object:
    """Normalize ``None`` and safely resolve supported string annotations."""
    if annotation is inspect.Parameter.empty:
        return annotation
    if annotation is None:
        return type(None)
    if not isinstance(annotation, str):
        return annotation

    try:
        tree = ast.parse(annotation, mode="eval")

        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and node.id.startswith("__"):
                return annotation

            if isinstance(node, ast.Attribute):
                if node.attr.startswith("_"):
                    return annotation
                if node.attr in _DANGEROUS_ATTRIBUTES:
                    return annotation

            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Name) and func.id in _DANGEROUS_CALLS:
                    return annotation
                if isinstance(func, ast.Attribute) and func.attr in _DANGEROUS_CALLS:
                    return annotation

        names: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                names.add(node.id)
            elif isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
                names.add(node.value.id)

        safe_globals: dict[str, Any] = {
            "__builtins__": {},
            "typing": typing,
        }

        for name in names:
            if name in _SAFE_ANNOTATION_BUILTINS:
                safe_globals[name] = getattr(builtins, name)

        for symbol in _TYPING_SYMBOLS:
            if symbol in names:
                safe_globals[symbol] = getattr(typing, symbol)

        result = eval(compile(tree, "<annotation>", "eval"), safe_globals)
        if result is None:
            return type(None)
        return result
    except Exception:
        return annotation


def get_origin(annotation: object) -> object | None:
    """Return an annotation origin, including non-standard generic objects."""
    origin = typing.get_origin(annotation)
    if origin is not None:
        return cast("object", origin)
    return cast("object | None", getattr(annotation, "__origin__", None))


def get_args(annotation: object) -> object:
    """Return generic annotation arguments or an empty tuple."""
    args = typing.get_args(annotation)
    if args:
        return cast("object", args)
    return cast("object", getattr(annotation, "__args__", ()))


def union_args(annotation: object) -> tuple[Any, ...] | None:
    """Return union members for PEP 604 and ``typing.Union`` aliases."""
    origin = get_origin(annotation)
    if origin is types.UnionType or origin is typing.Union:
        return cast("tuple[Any, ...]", get_args(annotation))
    return None
