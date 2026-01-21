from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    SUPABASE_PUBLISHABLE_KEY: str
    SECRET_KEY: str
    SUPABASE_URL: str

    model_config = SettingsConfigDict(
        case_sensitive=False,
        env_file=".env",
        env_file_encoding="utf-8",
    )


settings = Settings()
