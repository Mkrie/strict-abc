# strict-abc-lsp

![CI](https://github.com/Mkrie/strict-abc/actions/workflows/ci.yml/badge.svg)
[![codecov](https://img.shields.io/codecov/c/github/Mkrie/strict-abc?logo=codecov)](https://codecov.io/gh/Mkrie/strict-abc)
[![PyPI version](https://img.shields.io/pypi/v/strict-abc-lsp.svg)](https://pypi.org/project/strict-abc-lsp/)
[![Python versions](https://img.shields.io/pypi/pyversions/strict-abc-lsp.svg)](https://pypi.org/project/strict-abc-lsp/)
[![PyPI - Types](https://img.shields.io/pypi/types/strict-abc-lsp.svg)](https://pypi.org/project/strict-abc-lsp/)
[![PyPI Downloads](https://static.pepy.tech/personalized-badge/strict-abc-lsp?period=total&units=INTERNATIONAL_SYSTEM&left_color=BLACK&right_color=GREEN&left_text=downloads)](https://pepy.tech/projects/strict-abc-lsp)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![mypy](https://img.shields.io/badge/mypy-checked-2A6DB2.svg)](http://mypy-lang.org/)

`strict-abc-lsp` is a Python library that adds runtime signature validation for abstract base classes.

It provides `StrictABCMeta` and `StrictABC`, which check concrete implementations of abstract methods at class definition time and fail fast when a subclass violates LSP-friendly signature rules.

> **Distribution name:** `strict-abc-lsp`  
> **Import name:** `strict_abc`

---

## Why?

Python's standard `abc` module checks whether an abstract method is implemented, but it does not check whether the implementation preserves the original calling contract.

For example, this is allowed by standard `abc`:

```python
from abc import ABC, abstractmethod


class Base(ABC):
    @abstractmethod
    def process(self, data: dict, cache: bool = True) -> str: ...


class Impl(Base):
    def process(self, data: dict, cache: bool) -> str:
        return "ok"
```

The method is implemented, so Python considers the class concrete.

However, the parent contract allowed this call:

```python
obj.process(data)
```

The implementation above breaks it, because `cache` is no longer optional.

This is a violation of the Liskov Substitution Principle.

`strict-abc-lsp` detects such violations early, at class definition time.

---

## Installation

```bash
pip install strict-abc-lsp
```

The package is typed and ships with `py.typed`.

```python
import strict_abc
```

---

## Quickstart

```python
from abc import abstractmethod

from strict_abc import StrictABC


class BaseService(StrictABC):
    @abstractmethod
    def process(self, data: dict, cache: bool = True) -> str: ...


class ValidService(BaseService):
    def process(self, data: dict, cache: bool = True) -> str:
        return "ok"
```

This works.

But this raises `TypeError` (specifically `LSPViolation`) at class definition time:

```python
class InvalidService(BaseService):
    def process(self, data: dict, cache: bool) -> str:
        return "ok"
```

Error:

```text
TypeError: InvalidService.process: removing default value for 'cache'
strengthens precondition and violates LSP
```

---

## What it checks

`strict-abc-lsp` validates many common LSP-violating signature changes.

### 1. Removing default values

Not allowed:

```python
class Base(StrictABC):
    @abstractmethod
    def m(self, a: int = 1) -> None: ...


class Impl(Base):
    def m(self, a: int) -> None: ...
```

Allowed:

```python
class Base(StrictABC):
    @abstractmethod
    def m(self, a: int) -> None: ...


class Impl(Base):
    def m(self, a: int = 1) -> None: ...
```

Adding defaults weakens the precondition and is safe.

---

### 2. Adding new required parameters

Not allowed:

```python
class Base(StrictABC):
    @abstractmethod
    def m(self, a: int) -> None: ...


class Impl(Base):
    def m(self, a: int, b: int) -> None: ...
```

Allowed if the new parameter is optional:

```python
class Impl(Base):
    def m(self, a: int, b: int = 0) -> None: ...
```

---

### 3. Removing `*args` or `**kwargs`

Not allowed:

```python
class Base(StrictABC):
    @abstractmethod
    def m(self, *args: int) -> None: ...


class Impl(Base):
    def m(self) -> None: ...
```

Also not allowed:

```python
class Base(StrictABC):
    @abstractmethod
    def m(self, **kwargs: int) -> None: ...


class Impl(Base):
    def m(self) -> None: ...
```

Adding `*args` or `**kwargs` is allowed because it expands the accepted call surface.

---

### 4. Keyword compatibility

Keyword parameter names are part of the public calling contract.

Not allowed:

```python
class Base(StrictABC):
    @abstractmethod
    def connect(self, *, host: str) -> None: ...


class Impl(Base):
    def connect(self, *, address: str) -> None: ...
```

Parent callers may use:

```python
client.connect(host="localhost")
```

The implementation above breaks that call.

---

### 5. Descriptor compatibility

The implementation must preserve the descriptor type of the abstract method.

For example, a static method must remain a static method:

```python
class Base(StrictABC):
    @staticmethod
    @abstractmethod
    def parse(raw: str) -> dict: ...


class ValidImpl(Base):
    @staticmethod
    def parse(raw: str) -> dict:
        return {}
```

This raises `TypeError`:

```python
class InvalidImpl(Base):
    def parse(self, raw: str) -> dict:
        return {}
```

`strict-abc-lsp` understands:

- instance methods;
- `staticmethod`;
- `classmethod`;
- `property`.

---

### 6. Return type covariance

When enabled, return type annotations are checked for basic covariance.

Allowed:

```python
class Base(StrictABC):
    __strict_options__ = {"check_return_type": True}

    @abstractmethod
    def get(self) -> object: ...


class Impl(Base):
    def get(self) -> str:
        return "ok"
```

Not allowed:

```python
class Base(StrictABC):
    __strict_options__ = {"check_return_type": True}

    @abstractmethod
    def get(self) -> str: ...


class Impl(Base):
    def get(self) -> object:
        return object()
```

---

### 7. Async/sync compatibility

An abstract `async def` method must be implemented as an `async def` method, and a regular `def` must remain synchronous. Mixing them raises an error.

---

## Options

Validation behavior can be configured using `__strict_options__`.

```python
class Base(StrictABC):
    __strict_options__ = {
        "check_names": True,
        "check_defaults": True,
        "check_types": True,
        "check_types_contravariant": True,
        "check_return_type": True,
        "mode": "error",
    }

    @abstractmethod
    def fetch(self, url: str) -> bytes: ...
```

### Available options

| Option | Default | Description |
|---|---:|---|
| `check_names` | `False` | Require exact parameter name matching. |
| `check_defaults` | `True` | Forbid removing default values. |
| `check_types` | `False` | Require exact parameter type annotation matching. |
| `check_types_contravariant` | `False` | Require contravariant parameter types (child may widen the accepted type). Takes precedence over `check_types`. |
| `check_return_type` | `False` | Require covariant return type annotations. |
| `mode` | `"error"` | `"error"` raises `LSPViolation` (a `TypeError`), `"warn"` emits a `UserWarning`. |

Default configuration:

```python
{
    "check_names": False,
    "check_defaults": True,
    "check_types": False,
    "check_types_contravariant": False,
    "check_return_type": False,
    "mode": "error",
}
```

---

## Option inheritance

Options are merged through the MRO.

Example:

```python
class Base(StrictABC):
    __strict_options__ = {"check_types": True}

    @abstractmethod
    def m(self, a: int) -> None: ...


class Child(Base):
    __strict_options__ = {"check_names": True}

    def m(self, a: int) -> None: ...
```

In this case, both options are active:

```python
{
    "check_types": True,
    "check_names": True,
}
```

---

## Using the metaclass directly

You can use `StrictABCMeta` without inheriting from `StrictABC`:

```python
from abc import abstractmethod

from strict_abc import StrictABCMeta


class Base(metaclass=StrictABCMeta):
    @abstractmethod
    def run(self, timeout: int = 30) -> None: ...


class Impl(Base):
    def run(self, timeout: int = 30) -> None: ...
```

---

## Using the `@strict` decorator

If you already have a base class or metaclass hierarchy and cannot inherit from `StrictABC`, you can use the `@strict` class decorator to inject options:

```python
from abc import ABC, abstractmethod
from strict_abc import StrictABCMeta, strict

@strict(check_types=True, check_return_type=True)
class Base(ABC, metaclass=StrictABCMeta):
    @abstractmethod
    def run(self) -> None: ...
```

---

## Exempting methods

If you intentionally want to narrow the calling contract and acknowledge the LSP violation, you can mark a method with `@lsp_exempt`:

```python
from strict_abc import StrictABC, lsp_exempt
from abc import abstractmethod

class Base(StrictABC):
    @abstractmethod
    def process(self, data: dict, cache: bool = True) -> str: ...

class Impl(Base):
    @lsp_exempt
    def process(self, data: dict) -> str:
        return "ok"
```

---

## Relation to SOLID

This library is primarily focused on the **Liskov Substitution Principle**.

The Liskov Substitution Principle says that objects of a subtype should be usable in place of objects of the parent type without breaking the program.

`strict-abc-lsp` enforces part of this principle at the signature level:

- implementations must not strengthen preconditions;
- implementations must not remove accepted calling forms;
- implementations must not remove variadic parameters declared by the parent;
- implementations should preserve keyword-call compatibility;
- return types should remain covariant when checking is enabled;
- parameter types may widen (contravariance) when checking is enabled.

However, this library does **not** verify full behavioral substitution.

It does not check:

- business rules;
- invariants;
- side effects;
- exception guarantees;
- method semantics;
- thread-safety;
- performance contracts.

For behavioral contracts, consider tools such as `icontract` or design-by-contract approaches.

---

## How it differs from other tools

### Compared to `abc`

Standard `abc`:

```text
Checks whether abstract methods are implemented.
```

`strict-abc-lsp`:

```text
Also checks whether implementations preserve the abstract calling contract.
```

---

### Compared to `mypy` / `pyright`

Static type checkers can detect many incompatible overrides.

But they:

- require typed code;
- are not always used by plugin authors;
- do not protect runtime-generated classes;
- do not protect dynamically loaded extensions;
- may not be part of every deployment pipeline.

`strict-abc-lsp` provides an additional runtime safety layer.

It is not a replacement for static typing.

It is a complement to it.

---

## When to use

This library is especially useful for:

- plugin systems;
- frameworks;
- SDKs;
- public base classes;
- extension points;
- educational projects about LSP and OOP;
- projects where runtime safety is important;
- codebases where not all contributors use strict static typing.

---

## Limitations

`strict-abc-lsp` is a practical runtime checker, not a complete formal LSP verifier.

Current limitations include:

- parameter type contravariance is handled conservatively (e.g., basic subclasses and unions are supported, but complex generic aliases may not be fully resolved);
- generic return type covariance is handled conservatively;
- overloaded functions are not fully analyzed;
- custom descriptors may not be fully supported;
- behavioral semantics are not checked;
- complex signature reordering may still produce edge cases.

---

## Requirements

- Python 3.10+

---

## Development

The project uses:

- [Poetry](https://python-poetry.org/)
- [pytest](https://pytest.org/)
- [pytest-cov](https://pytest-cov.readthedocs.io/)
- [Ruff](https://github.com/astral-sh/ruff)
- [mypy](https://mypy-lang.org/)
- [pre-commit](https://pre-commit.com/)

Install dependencies:

```bash
make install
```

Run lint, type check, tests, build and dist check:

```bash
make all
```

Run tests with coverage:

```bash
make cov
```

Install pre-commit hooks:

```bash
make pre-commit-install
```

---

## Project layout

```text
strict-abc/
├── src/
│   └── strict_abc/
│       ├── __init__.py
│       ├── _meta.py
│       └── py.typed
├── tests/
│   └── test_strict_abc.py
├── .github/
│   └── workflows/
│       └── ci.yml
├── pyproject.toml
├── Makefile
├── README.md
└── LICENSE
```

---

## Publishing

This project is published as:

```text
strict-abc-lsp
```

Install it with:

```bash
pip install strict-abc-lsp
```

Import it with:

```bash
import strict_abc
```

---

## Versioning

This project follows semantic versioning:

```text
MAJOR.MINOR.PATCH
```

- `PATCH` — backward-compatible bug fixes;
- `MINOR` — backward-compatible new features;
- `MAJOR` — incompatible API changes.

---

## License

MIT
```