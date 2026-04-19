"""Shared session helpers for runnable gemstone-py examples."""

from typing import Any

import gemstone_py as gemstone

WRITE_POLICY = gemstone.TransactionPolicy.COMMIT_ON_SUCCESS
READ_POLICY = gemstone.TransactionPolicy.ABORT_ON_EXIT
MANUAL_POLICY = gemstone.TransactionPolicy.MANUAL

_CONFIG: gemstone.GemStoneConfig | None = None


def example_config() -> gemstone.GemStoneConfig:
    global _CONFIG
    if _CONFIG is None:
        try:
            _CONFIG = gemstone.GemStoneConfig.from_env()
        except gemstone.GemStoneConfigurationError as exc:
            raise SystemExit(
                f"{exc}\n"
                "Set GS_USERNAME and GS_PASSWORD before running this example."
            ) from exc
    return _CONFIG


def example_session(
    *,
    transaction_policy: gemstone.TransactionPolicy | str = WRITE_POLICY,
    **kwargs: Any,
) -> gemstone.GemStoneSession:
    return gemstone.GemStoneSession(
        config=example_config(),
        transaction_policy=transaction_policy,
        **kwargs,
    )
