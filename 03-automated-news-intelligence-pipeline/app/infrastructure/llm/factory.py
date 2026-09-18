"""LLM client factory for live and demo modes."""

from app.application.ports import LlmClient
from app.config import PROJECT_ROOT, Settings
from app.infrastructure.llm.mock_client import MockDigestClient
from app.infrastructure.llm.openai_client import OpenAIDigestClient


def build_llm_client(settings: Settings) -> LlmClient:
    """Return the OpenAI client in live mode and the fixture client in demo mode."""
    if settings.app_mode == "demo":
        demo_dir = PROJECT_ROOT / "demo" / "openai"
        return MockDigestClient(
            happy_path=demo_dir / "happy_path.json",
            invalid_candidate=demo_dir / "invalid_candidate.json",
            repair_ok=demo_dir / "repair_ok.json",
        )

    return OpenAIDigestClient(settings)
