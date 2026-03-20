"""
Prompts module for ACE system.
Contains all prompts for Generator, Reflector, and Curator agents.
"""

from .curator import CURATOR_PROMPT, CURATOR_PROMPT_NO_GT
from .generator import GENERATOR_PROMPT
from .reflector import REFLECTOR_PROMPT, REFLECTOR_PROMPT_NO_GT

__all__ = [
    # Generator prompts
    "GENERATOR_PROMPT",
    # Reflector prompts
    "REFLECTOR_PROMPT",
    "REFLECTOR_PROMPT_NO_GT",
    # Curator prompts
    "CURATOR_PROMPT",
    "CURATOR_PROMPT_NO_GT",
]
