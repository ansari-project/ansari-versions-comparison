import logging
from functools import lru_cache
from typing import Union, Optional
from pydantic_settings import BaseSettings
from pydantic import SecretStr, PostgresDsn, DirectoryPath, Field, AnyUrl, validator

logger = logging.getLogger(__name__)

class Settings(BaseSettings):
    
    MAX_THREAD_NAME_LENGTH: int = Field(default=100)

    OPENAI_API_KEY: SecretStr
    PGPASSWORD: SecretStr
    KALEMAT_API_KEY: SecretStr
    VECTARA_AUTH_TOKEN: SecretStr
    VECTARA_CUSTOMER_ID: str
    VECTARA_CORPUS_ID: str

    template_dir: DirectoryPath = Field(default="/home/user/app/resources/prompts")

    MODEL: str = Field(default="gpt-4o-2024-05-13")
    MAX_FUNCTION_TRIES: int = Field(default=3)
    MAX_FAILURES: int = Field(default=1)
    SYSTEM_PROMPT_FILE_NAME: str = Field(default="system_msg_fn")

    # A/B Testing database connection configuration
    AB_TESTING_DB_NAME: str
    AB_TESTING_DB_USER: str
    AB_TESTING_DB_PASSWORD: SecretStr
    AB_TESTING_DB_HOST: AnyUrl
    AB_TESTING_DB_PORT: int
    
    # A/B Testing environment variables
    AB_TESTING_EXPERIMENT_ID: int
    AB_TESTING_MODEL_1_ID: int
    AB_TESTING_MODEL_2_ID: int

@lru_cache()
def get_settings() -> Settings:
    try:
        settings = Settings()
        return settings
    except Exception as e:
        logger.error(f"Error loading settings: {e}")
        raise
