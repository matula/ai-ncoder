import os
import sys

import pytest

# Add project root to sys.path so we can import project modules
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJECT_ROOT)

_MODEL_PATH = os.path.join(
    _PROJECT_ROOT, "models", "qwen2.5-coder-0.5b-instruct-q8_0.gguf"
)


@pytest.fixture(scope="session")
def ai_engine():
    """Load the AI model once for the entire test session."""
    from ai_engine import AIEngine

    return AIEngine(_MODEL_PATH)
