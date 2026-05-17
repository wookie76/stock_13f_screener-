from __future__ import annotations

from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    """Runtime settings loaded from environment or .env."""

    model_config = SettingsConfigDict(
        env_prefix="STOCK13F_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    data_dir: Path = Path("data")
    sec_company_name: str = "Stock13FScreener"
    sec_email: str = "example@example.com"
    sec_requests_per_second: float = 5.0
    openfigi_api_key: str | None = Field(default=None, validation_alias="OPENFIGI_API_KEY")
    openfigi_timeout_seconds: float = 30.0
    openfigi_max_retries: int = 5
    random_seed: int = 42

    @field_validator("sec_requests_per_second")
    @classmethod
    def _validate_sec_rate(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("sec_requests_per_second must be positive")
        if value > 10:
            raise ValueError("SEC fair-access rate must not exceed 10 requests/second")
        return value

    @property
    def raw_dir(self) -> Path:
        return self.data_dir / "raw" / "sec_filings"

    @property
    def silver_dir(self) -> Path:
        return self.data_dir / "silver"

    @property
    def gold_dir(self) -> Path:
        return self.data_dir / "gold"


def get_settings() -> AppSettings:
    return AppSettings()
