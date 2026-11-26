"""Exceptions raised by :mod:`strict_abc`."""


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
