"""Deterministic differential tests for signature compatibility."""

import inspect
import itertools
import random
from collections.abc import Iterator
from typing import Any

from strict_abc import LSPViolation, StrictABCMeta

_PARAMETER = inspect.Parameter
_REGULAR_KINDS = (
    _PARAMETER.POSITIONAL_ONLY,
    _PARAMETER.POSITIONAL_OR_KEYWORD,
    _PARAMETER.KEYWORD_ONLY,
)
_ALL_KINDS = _REGULAR_KINDS + (
    _PARAMETER.VAR_POSITIONAL,
    _PARAMETER.VAR_KEYWORD,
)


def _random_signature(rng: random.Random) -> inspect.Signature | None:
    params = []
    for index in range(rng.randrange(0, 5)):
        kind = rng.choice(_ALL_KINDS)
        default = (
            rng.choice([_PARAMETER.empty, _PARAMETER.empty, index])
            if kind in _REGULAR_KINDS
            else _PARAMETER.empty
        )
        params.append(_PARAMETER(chr(97 + index), kind, default=default))
    rng.shuffle(params)
    try:
        return inspect.Signature(params)
    except ValueError:
        return None


def _bind(
    signature: inspect.Signature,
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
) -> inspect.BoundArguments:
    has_var_keyword = any(
        parameter.kind == _PARAMETER.VAR_KEYWORD
        for parameter in signature.parameters.values()
    )
    positional_only = {
        parameter.name
        for parameter in signature.parameters.values()
        if parameter.kind == _PARAMETER.POSITIONAL_ONLY
    }
    if not has_var_keyword and positional_only.intersection(kwargs):
        raise TypeError("positional-only argument passed as keyword")
    return signature.bind(*args, **kwargs)


def _calls(signature: inspect.Signature) -> Iterator[tuple[tuple[Any, ...], dict[str, Any]]]:
    params = list(signature.parameters.values())
    positional = [
        parameter
        for parameter in params
        if parameter.kind
        in (_PARAMETER.POSITIONAL_ONLY, _PARAMETER.POSITIONAL_OR_KEYWORD)
    ]
    keyword = [
        parameter.name
        for parameter in params
        if parameter.kind
        in (_PARAMETER.POSITIONAL_OR_KEYWORD, _PARAMETER.KEYWORD_ONLY)
    ]
    extra_positional = (
        2 if any(parameter.kind == _PARAMETER.VAR_POSITIONAL for parameter in params) else 0
    )
    has_var_keyword = any(parameter.kind == _PARAMETER.VAR_KEYWORD for parameter in params)

    for positional_count in range(len(positional) + extra_positional + 1):
        for mask in itertools.product((False, True), repeat=len(keyword)):
            extra_keyword_options = (False, True) if has_var_keyword else (False,)
            for add_extra_keyword in extra_keyword_options:
                args = tuple(range(100, 100 + positional_count))
                kwargs = {
                    name: index
                    for index, (name, use) in enumerate(zip(keyword, mask, strict=True), 200)
                    if use
                }
                if add_extra_keyword:
                    kwargs["extra"] = 300
                try:
                    _bind(signature, args, kwargs)
                except TypeError:
                    continue
                yield args, kwargs


def _violations(
    parent: inspect.Signature,
    child: inspect.Signature,
) -> list[LSPViolation]:
    result: list[LSPViolation] = []
    StrictABCMeta._validate_signature(
        meth_name="m",
        sig_parent=parent,
        sig_child=child,
        parent_descriptor="staticmethod",
        child_descriptor="staticmethod",
        check_names=False,
        check_defaults=True,
        check_types=False,
        check_types_contravariant=False,
        check_return_type=False,
        class_name="Impl",
        violations=result,
    )
    return result


def test_randomized_signature_compatibility_matches_call_binding() -> None:
    rng = random.Random(20261128)

    for _ in range(2000):
        parent = _random_signature(rng)
        child = _random_signature(rng)
        if parent is None or child is None:
            continue

        rejected_call = None
        for args, kwargs in _calls(parent):
            try:
                _bind(child, args, kwargs)
            except TypeError:
                rejected_call = (args, kwargs)
                break

        violations = _violations(parent, child)
        if rejected_call is not None:
            assert violations, (
                f"Accepted incompatible signatures: parent={parent}, child={child}, "
                f"rejected call={rejected_call}"
            )
            continue

        parent_is_finite = all(
            parameter.kind in _REGULAR_KINDS for parameter in parent.parameters.values()
        )
        if parent_is_finite:
            assert not violations, (
                f"Rejected compatible signatures: parent={parent}, child={child}, "
                f"violations={[violation.reason for violation in violations]}"
            )
