"""Pure validation of parent and child calling contracts."""

import inspect
from dataclasses import dataclass
from typing import Literal

from strict_abc._annotations import normalize_annotation
from strict_abc._descriptors import DescriptorKind
from strict_abc._errors import LSPViolation
from strict_abc._types import is_param_compatible_contravariant, is_return_compatible


@dataclass(frozen=True)
class SignatureOptions:
    """Boolean checks applied to a signature pair."""

    check_names: bool = False
    check_defaults: bool = True
    check_types: bool = False
    check_types_contravariant: bool = False
    check_return_type: bool = False


@dataclass(frozen=True)
class ParameterPair:
    """A parent parameter and the child parameter accepting one call form."""

    parent: inspect.Parameter
    child: inspect.Parameter
    channel: Literal["position", "name", "var_pos", "var_kw"]
    checked_position: bool = False


def validate_signature(
    *,
    meth_name: str,
    sig_parent: inspect.Signature,
    sig_child: inspect.Signature,
    parent_descriptor: DescriptorKind,
    child_descriptor: DescriptorKind,
    options: SignatureOptions,
    class_name: str,
) -> list[LSPViolation]:
    """Return violations found between a parent contract and its implementation."""
    violations: list[LSPViolation] = []

    def add_violation(reason: str) -> None:
        violations.append(LSPViolation(class_name, meth_name, reason))

    def check_annotation(
        parent_param: inspect.Parameter,
        child_param: inspect.Parameter,
        label: str,
    ) -> None:
        if not (options.check_types or options.check_types_contravariant):
            return

        parent_has_annotation = parent_param.annotation is not inspect.Parameter.empty
        child_has_annotation = child_param.annotation is not inspect.Parameter.empty

        if parent_has_annotation and not child_has_annotation:
            add_violation(f"missing type annotation for '{label}'")
            return
        if not (parent_has_annotation and child_has_annotation):
            return

        parent_annotation = normalize_annotation(parent_param.annotation)
        child_annotation = normalize_annotation(child_param.annotation)

        if options.check_types_contravariant:
            if not is_param_compatible_contravariant(
                parent_annotation, child_annotation
            ):
                add_violation(
                    f"parameter type for '{label}' is not contravariant "
                    f"(parent: {parent_annotation}, child: {child_annotation})"
                )
        elif parent_annotation != child_annotation:
            add_violation(
                f"type annotation mismatch for '{label}' "
                f"(expected {parent_annotation}, got {child_annotation})"
            )

    def check_default(
        parent_param: inspect.Parameter,
        child_param: inspect.Parameter,
    ) -> None:
        if (
            options.check_defaults
            and parent_param.default is not inspect.Parameter.empty
            and child_param.default is inspect.Parameter.empty
        ):
            add_violation(
                f"removing default value for '{parent_param.name}' "
                "strengthens precondition and violates LSP"
            )

    parent_params = list(sig_parent.parameters.values())
    child_params = list(sig_child.parameters.values())

    if parent_descriptor != "staticmethod" and parent_params:
        parent_params = parent_params[1:]
    if child_descriptor != "staticmethod" and child_params:
        child_params = child_params[1:]

    parent_var_pos = next(
        (
            parameter
            for parameter in parent_params
            if parameter.kind == inspect.Parameter.VAR_POSITIONAL
        ),
        None,
    )
    parent_var_kw = next(
        (
            parameter
            for parameter in parent_params
            if parameter.kind == inspect.Parameter.VAR_KEYWORD
        ),
        None,
    )
    child_var_pos = next(
        (
            parameter
            for parameter in child_params
            if parameter.kind == inspect.Parameter.VAR_POSITIONAL
        ),
        None,
    )
    child_var_kw = next(
        (
            parameter
            for parameter in child_params
            if parameter.kind == inspect.Parameter.VAR_KEYWORD
        ),
        None,
    )

    if parent_var_pos is not None and child_var_pos is None:
        add_violation("removed *args from parent signature (violates LSP)")
    if parent_var_kw is not None and child_var_kw is None:
        add_violation("removed **kwargs from parent signature (violates LSP)")

    if parent_var_pos is not None and child_var_pos is not None:
        check_annotation(parent_var_pos, child_var_pos, f"*{parent_var_pos.name}")
    if parent_var_kw is not None and child_var_kw is not None:
        check_annotation(parent_var_kw, child_var_kw, f"**{parent_var_kw.name}")

    positional_kinds = (
        inspect.Parameter.POSITIONAL_ONLY,
        inspect.Parameter.POSITIONAL_OR_KEYWORD,
    )
    keyword_accessible_kinds = (
        inspect.Parameter.POSITIONAL_OR_KEYWORD,
        inspect.Parameter.KEYWORD_ONLY,
    )

    parent_pos = [
        parameter for parameter in parent_params if parameter.kind in positional_kinds
    ]
    child_pos = [
        parameter for parameter in child_params if parameter.kind in positional_kinds
    ]
    parent_kw = {
        parameter.name: parameter
        for parameter in parent_params
        if parameter.kind == inspect.Parameter.KEYWORD_ONLY
    }
    child_kw = {
        parameter.name: parameter
        for parameter in child_params
        if parameter.kind == inspect.Parameter.KEYWORD_ONLY
    }
    child_by_keyword_name = {
        parameter.name: parameter
        for parameter in child_params
        if parameter.kind in keyword_accessible_kinds
    }
    child_param_names = {parameter.name for parameter in child_params}

    positional_pairs = [
        ParameterPair(parent, child, "position", checked_position=True)
        for parent, child in zip(parent_pos, child_pos, strict=False)
    ]
    positional_pairs_by_name = {
        pair.parent.name: pair for pair in positional_pairs
    }

    parent_keyword_params = [
        parameter
        for parameter in parent_params
        if parameter.kind in keyword_accessible_kinds
    ]
    keyword_pairs: list[ParameterPair | None] = []
    for parent in parent_keyword_params:
        child = child_by_keyword_name.get(parent.name)
        if child is not None:
            positional_pair = positional_pairs_by_name.get(parent.name)
            keyword_pairs.append(
                ParameterPair(
                    parent,
                    child,
                    "name",
                    checked_position=(
                        positional_pair is not None
                        and positional_pair.child.name == child.name
                    ),
                )
            )
        elif child_var_kw is not None:
            keyword_pairs.append(ParameterPair(parent, child_var_kw, "var_kw"))
        else:
            keyword_pairs.append(None)

    stripped_parent_signature = inspect.Signature(parent_params)

    def has_keyword_collision(position: int, child_name: str) -> bool:
        if not any(
            parameter.name == child_name
            and parameter.kind in keyword_accessible_kinds
            for parameter in parent_params
        ):
            return False

        positional_limit = len(parent_pos)
        if parent_var_pos is not None:
            positional_limit = max(positional_limit, position + 1)

        for positional_count in range(position + 1, positional_limit + 1):
            args = (None,) * positional_count
            kwargs = {child_name: None}
            positional_names = {
                parameter.name
                for parameter in parent_pos[:positional_count]
                if parameter.kind == inspect.Parameter.POSITIONAL_OR_KEYWORD
            }
            for parameter in parent_params:
                if (
                    parameter.kind in keyword_accessible_kinds
                    and parameter.default is inspect.Parameter.empty
                    and parameter.name not in positional_names
                    and parameter.name not in kwargs
                ):
                    kwargs[parameter.name] = None
            try:
                stripped_parent_signature.bind(*args, **kwargs)
            except TypeError:
                continue
            return True
        return False

    reported_name_mismatches: set[str] = set()

    if len(child_pos) < len(parent_pos) and child_var_pos is None:
        add_violation("cannot accept parent positional parameters without *args")

    allowed_kind_expansions = {
        (
            inspect.Parameter.POSITIONAL_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
        ),
    }

    for pair in positional_pairs:
        parent = pair.parent
        child = pair.child
        check_default(parent, child)

        if (
            parent.kind != child.kind
            and (parent.kind, child.kind) not in allowed_kind_expansions
        ):
            keyword_is_preserved = (
                parent.kind == inspect.Parameter.POSITIONAL_OR_KEYWORD
                and child.kind == inspect.Parameter.POSITIONAL_ONLY
                and (
                    parent.name != child.name
                    or child.default is not inspect.Parameter.empty
                )
                and (
                    child_var_kw is not None
                    or parent.name in child_by_keyword_name
                )
            )
            if not keyword_is_preserved:
                add_violation(
                    f"parameter '{parent.name}' kind transition "
                    f"{parent.kind.name} -> {child.kind.name} restricts call syntax "
                    "and violates LSP"
                )

        if options.check_names and parent.name != child.name:
            reported_name_mismatches.add(parent.name)
            add_violation(
                f"parameter name mismatch "
                f"(expected '{parent.name}', got '{child.name}')"
            )

        if (
            parent.kind == inspect.Parameter.POSITIONAL_OR_KEYWORD
            and parent.name != child.name
        ):
            if child.default is inspect.Parameter.empty:
                add_violation(
                    f"cannot accept parent keyword parameter '{parent.name}' "
                    "because corresponding child parameter has no default"
                )
            if parent.name not in child_by_keyword_name and child_var_kw is None:
                add_violation(
                    f"cannot accept parent keyword parameter '{parent.name}' "
                    "without **kwargs"
                )

        check_annotation(parent, child, parent.name)

    for position, child in enumerate(child_pos):
        parent_positional = parent_pos[position] if position < len(parent_pos) else None
        if (
            (parent_positional is None or parent_positional.name != child.name)
            and child.kind == inspect.Parameter.POSITIONAL_OR_KEYWORD
            and has_keyword_collision(position, child.name)
        ):
            add_violation(
                f"parameter '{child.name}' can receive multiple values "
                "for a valid parent call"
            )

    if child_var_pos is not None:
        for parent in parent_pos[len(child_pos) :]:
            check_annotation(parent, child_var_pos, parent.name)

    for child in child_pos[len(parent_pos) :]:
        if child.default is inspect.Parameter.empty:
            parent_keyword = parent_kw.get(child.name)
            if (
                child.kind == inspect.Parameter.POSITIONAL_OR_KEYWORD
                and parent_keyword is not None
                and parent_keyword.default is inspect.Parameter.empty
            ):
                continue
            add_violation(
                f"new required parameter '{child.name}' "
                "strengthens precondition and violates LSP"
            )

    parent_keyword_names = {
        parameter.name for parameter in parent_keyword_params
    }

    for parent, keyword_pair in zip(parent_keyword_params, keyword_pairs, strict=True):
        if keyword_pair is None:
            add_violation(
                f"cannot accept parent keyword parameter '{parent.name}' "
                "without **kwargs"
            )
            continue

        child = keyword_pair.child
        if keyword_pair.channel == "var_kw":
            check_annotation(parent, child, parent.name)
            if (
                options.check_names
                and parent.name not in child_param_names
                and parent.name not in reported_name_mismatches
            ):
                add_violation(
                    f"parameter name mismatch "
                    f"(expected '{parent.name}', got '**kwargs')"
                )
            continue

        if (
            parent.kind == inspect.Parameter.POSITIONAL_OR_KEYWORD
            and child.kind == inspect.Parameter.KEYWORD_ONLY
            and child.default is inspect.Parameter.empty
        ):
            add_violation(
                f"keyword-only implementation of positional-or-keyword parameter "
                f"'{parent.name}' must have a default value or *args"
            )

        if not keyword_pair.checked_position:
            check_default(parent, child)
            check_annotation(parent, child, parent.name)

    for keyword_name, child in child_kw.items():
        if (
            keyword_name not in parent_keyword_names
            and child.default is inspect.Parameter.empty
        ):
            add_violation(
                f"new required keyword-only parameter '{keyword_name}' "
                "strengthens precondition and violates LSP"
            )

    if options.check_return_type:
        parent_return = sig_parent.return_annotation
        child_return = sig_child.return_annotation
        if (
            parent_return is not inspect.Signature.empty
            and child_return is inspect.Signature.empty
        ):
            add_violation("missing return type annotation")
        elif not is_return_compatible(parent_return, child_return):
            add_violation(
                f"return type not covariant "
                f"(expected {parent_return}, got {child_return})"
            )

    return violations
