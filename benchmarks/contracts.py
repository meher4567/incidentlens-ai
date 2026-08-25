"""Shared fail-closed contracts for benchmark commands."""


class BenchmarkContractError(RuntimeError):
    """Raised when a benchmark cannot produce a meaningful measurement."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise BenchmarkContractError(message)
