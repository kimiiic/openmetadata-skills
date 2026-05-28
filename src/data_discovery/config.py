from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    host: str | None
    token: str | None
    timeout: str | None = None
    verify_ssl: str | None = None
    max_retries: str | None = None
    retry_delay: str | None = None

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            host=os.getenv("AI_SDK_HOST"),
            token=os.getenv("AI_SDK_TOKEN"),
            timeout=os.getenv("AI_SDK_TIMEOUT"),
            verify_ssl=os.getenv("AI_SDK_VERIFY_SSL"),
            max_retries=os.getenv("AI_SDK_MAX_RETRIES"),
            retry_delay=os.getenv("AI_SDK_RETRY_DELAY"),
        )

    def validate_for_runtime(self) -> None:
        missing = [name for name, value in (("AI_SDK_HOST", self.host), ("AI_SDK_TOKEN", self.token)) if not value]
        if missing:
            raise RuntimeError(f"Missing required environment variables: {', '.join(missing)}")
