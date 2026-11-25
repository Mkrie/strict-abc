"""Configuration for runtime signature validation."""

from collections.abc import Mapping
from typing import Any, Literal, TypedDict, cast


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


def get_options(cls: type[Any]) -> StrictOptions:
    """Merge ``__strict_options__`` across the MRO with subclass precedence."""
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
