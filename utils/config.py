"""
utils/config.py

Centralised configuration for the Kalb Contract Reviewer.

All OpenAI credentials and model names are read from .env here.
Every agent file that calls OpenAI imports from this module —
never from os or dotenv directly.
"""

from dotenv import load_dotenv
import os

load_dotenv()

OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
FILTER_MODEL:   str = os.getenv("FILTER_MODEL",   "gpt-4.1-mini")
ANALYSIS_MODEL: str = os.getenv("ANALYSIS_MODEL", "gpt-4.1-mini")


def get_openai_client():
    """Return a configured OpenAI client instance.

    Reads the API key from the module-level constant so the key is
    resolved at call time (useful in test environments that override
    OPENAI_API_KEY after import).

    Returns:
        openai.OpenAI: Ready-to-use client.

    Raises:
        ValueError: If OPENAI_API_KEY is not set.
    """
    from openai import OpenAI

    key = OPENAI_API_KEY or os.getenv("OPENAI_API_KEY", "")
    if not key:
        raise ValueError(
            "OPENAI_API_KEY is not set. "
            "Add it to your .env file."
        )
    return OpenAI(api_key=key)
