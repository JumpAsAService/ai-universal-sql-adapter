import os
from functools import lru_cache
from typing import Literal

from pydantic import BaseModel, Field, Json, SecretStr, computed_field
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    SettingsError,
    TomlConfigSettingsSource,
)


class OpenaiSettings(BaseModel):
    """Base model for openai compatible providers"""

    base_url: str = Field(..., description="base url for openai")
    secret_key: SecretStr = Field(..., description="secret key for openai")

    def __str__(self) -> str:
        return super().__str__()


class RedisSettings(BaseModel):
    host: str = Field(default="localhost", description="Redis host")
    port: int = Field(default=6379, description="Redis port")
    db: int = Field(default=0, description="Redis database number")
    password: SecretStr = Field(..., description="Redis password")

    @computed_field
    @property
    def url(self) -> str:
        if self.password:
            return f"redis://:{self.password.get_secret_value()}@{self.host}:{self.port}/{self.db}"
        return f"redis://{self.host}:{self.port}/{self.db}"

    def __str__(self):
        return f"RedisSettings(host={self.host}, port={self.port}, db={self.db})"


class DatabaseSettings(BaseModel):
    """Base model for database connections"""

    host: str = Field(..., description="database host")
    username: SecretStr = Field(..., description="database username")
    password: SecretStr = Field(..., description="database password")
    port: int = Field(..., description="database port")
    dialect: Literal["clickhouse"] = Field(..., description="database dialect")
    secure: bool = Field(
        True, description="if the database connection should be secure"
    )


class UserAllowance(BaseModel):
    id: int
    username: str
    password: SecretStr
    tables: list[str] = Field(..., min_length=1)


class AllowanceSettings(BaseModel):
    mapping: Json[dict[str, UserAllowance]]

    def __str__(self) -> str:
        return super().__str__()


class Settings(BaseSettings):
    openai: dict[str, OpenaiSettings] = Field(default_factory=dict)
    database: dict[str, DatabaseSettings] = Field(default_factory=dict)
    allowance: AllowanceSettings
    redis: RedisSettings

    model_config = SettingsConfigDict(
        env_nested_delimiter="__",
        extra="ignore",
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:

        environment: str = os.getenv("APP_ENV", "development")

        if environment == "production":
            return (init_settings, env_settings)
        elif environment == "development":
            return (
                init_settings,
                env_settings,
                TomlConfigSettingsSource(settings_cls, toml_file="config.toml"),
            )
        else:
            raise SettingsError(
                f"Settings errors: no correct environment spec (APP_ENV must be one of 'production' or 'development', actual '{environment}' not accepted)"
            )


@lru_cache
def get_settings() -> Settings:
    return Settings()
