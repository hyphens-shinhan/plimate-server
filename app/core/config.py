import os

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    SUPABASE_KEY: str
    SERVICE_KEY: str
    SUPERBASE_URL: str
    SQLALCHEMY_DATABASE_URL: str

    POSTGRES_PASSWORD: str
    POSTGRES_USER: str
    POSTGRES_DB: str

    model_config = SettingsConfigDict(
        case_sensitive=False,
        env_file=".env",
        env_file_encoding="utf-8",
    )


settings = Settings()
