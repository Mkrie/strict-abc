"""strict-abc-lsp: runtime LSP signature validation for abstract base classes.

Distribution name:
    ``strict-abc-lsp``

Import name:
    ``strict_abc``
"""

from strict_abc._meta import (
    DescriptorKind,
    LSPViolation,
    StrictABC,
    StrictABCMeta,
    StrictOptions,
    __version__,
    lsp_exempt,
    strict,
)

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