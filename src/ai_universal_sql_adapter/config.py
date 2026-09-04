from pydantic_settings import BaseSettings, SettingsConfigDict, TomlConfigSettingsSource, PydanticBaseSettingsSource
from pydantic_settings.exceptions import SettingsError
from pydantic import BaseModel, SecretStr, Field
from typing import Optional, Dict, cast
import os
from functools import lru_cache

class OpenaiProviderSettings(BaseModel):
    base_url: str = Field(..., description="Base url for the api usage")
    access_id: Optional[str] = Field(None, description="Access Key to connect to the api")
    secret_key: SecretStr = Field(..., description="Secret id for the api")

    def __str__(self) -> str:
        return super().__str__()

class DatabaseSettings(BaseModel):
    dialect: str = Field(..., description="Database type, supported by ibis, check https://pypi.org/project/ibis-framework/")
    host: str = Field(..., description="Database host")
    username: SecretStr = Field(..., description="Database username")
    password: SecretStr = Field(..., description="Database description")
    port: int = Field(..., description="Database exposed port")
    secure: bool = Field(True, description="If the Database connection must be secure")

    def __str__(self) -> str:
        return super().__str__()

class Settings(BaseSettings):
    openai: Dict[str, OpenaiProviderSettings] = Field(default_factory=dict)
    database: Dict[str, DatabaseSettings] = Field(default_factory=dict)

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
        
        environment: str = cast(str, os.getenv('APP_ENV', 'development'))

        if environment == 'production':
            return (init_settings, env_settings)
        elif environment == 'development':
            return (init_settings, env_settings, TomlConfigSettingsSource(settings_cls, toml_file='config.toml'))
        else:
            raise SettingsError(f"Settings errors: no correct environment spec (APP_ENV must be one of 'production' or 'development')")

    def __str__(self) -> str:
        return f"Settings(OpenaiSettings={self.openai}, DatabaseSettings=({self.database}))"

@lru_cache
def get_settings() -> Settings:
    """ Return a Settings object with secrets"""
    return Settings()