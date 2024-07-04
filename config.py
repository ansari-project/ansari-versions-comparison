import logging
from functools import lru_cache
from typing import Union, Optional
from pydantic_settings import BaseSettings
from pydantic import SecretStr, PostgresDsn, DirectoryPath, Field, validator

logger = logging.getLogger(__name__)

class Settings(BaseSettings):
    
    DATABASE_URL: PostgresDsn = Field(default="postgresql://mwk@localhost:5432/mwk")
    MAX_THREAD_NAME_LENGTH: int = Field(default=100)

    OPENAI_API_KEY: SecretStr
    PGPASSWORD: SecretStr
    KALEMAT_API_KEY: SecretStr
    VECTARA_AUTH_TOKEN: SecretStr
    VECTARA_CUSTOMER_ID: str
    VECTARA_CORPUS_ID: str

    template_dir: DirectoryPath = Field(default="/home/user/app/resources/templates")

    MODEL: str = Field(default="gpt-4o-2024-05-13")
    MAX_FUNCTION_TRIES: int = Field(default=3)
    MAX_FAILURES: int = Field(default=1)
    SYSTEM_PROMPT_FILE_NAME: str = Field(default="system_msg_fn")

@lru_cache()
def get_settings() -> Settings:
    try:
        settings = Settings()
        return settings
    except Exception as e:
        logger.error(f"Error loading settings: {e}")
        raise
