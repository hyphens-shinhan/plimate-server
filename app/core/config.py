from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    SECRET_KEY: str
    SUPABASE_URL: str

    @property
    def AVATAR_BUCKET_URL(self) -> str:
        # Construct it dynamically
        return f"{self.SUPABASE_URL}/storage/v1/object/public/avatars/default/"

    model_config = SettingsConfigDict(
        case_sensitive=False,
        env_file=".env",
        env_file_encoding="utf-8",
    )


settings = Settings()
