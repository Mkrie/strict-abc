# Changelog

All notable changes to this project will be documented in this file.

## 0.3.0

### Added

- Added `LSPViolation`, a `TypeError` subclass with additional attributes:
  - `cls_name`;
  - `meth_name`;
  - `reason`.
- Added `lsp_exempt` decorator to explicitly exempt a method from LSP signature validation.
- Added `strict` class decorator to inject `__strict_options__` without subclassing `StrictABC`.
- Added `check_types_contravariant` option for contravariant parameter type checking.
- Added `mode` option:
  - `"error"` raises violations;
  - `"warn"` emits warnings instead of raising.
- Added async/sync mismatch detection for abstract method implementations.
- Added collection of multiple signature violations before raising or warning.
- Added support for base classes exposing `__abstractmethods__` as a plain `set`, in addition to `frozenset`.
- Added safer normalization of string annotations, including limited AST-based evaluation for PEP 563-style annotations.
- Added signature unwrapping via `inspect.unwrap`, improving compatibility with decorated methods.
- Expanded test coverage for edge cases, descriptors, options merging, warnings mode, async checks, and annotation handling.

### Changed

- Public API now exports:
  - `LSPViolation`;
  - `lsp_exempt`;
  - `strict`.
- Signature validation failures now raise `LSPViolation` instead of plain `TypeError`.
  This remains backward compatible for code catching `TypeError`.
- Validation order is now more deterministic because parent abstract methods are processed in sorted order.
- Improved error messages for descriptor mismatches, keyword-only transitions, and signature violations.
- `StrictOptions` now includes `check_types_contravariant` and `mode`.
- Default `StrictABC.__strict_options__` now explicitly includes all supported options.
- `__version__` is now defined in `strict_abc._meta` and re-exported by the package.

### Fixed

- Avoid duplicate violation reports for positional-or-keyword parameters that are already checked in the positional compatibility pass.
- Handle `inspect.Parameter.empty` safely during annotation normalization.
- Better handling of wrapped functions when inspecting signatures.
- More defensive skipping of unreadable or unsupported descriptors instead of failing class creation.
- Improved handling of abstract method collections that are not strictly `frozenset` objects.

## 0.1.0

Initial release.
