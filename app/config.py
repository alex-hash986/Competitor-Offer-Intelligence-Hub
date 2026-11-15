from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "sqlite:///./competitor_intel.db"
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
VERSION = "0.1.0"
