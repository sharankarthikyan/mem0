"""Tests for the default fact-extraction prompt wiring in get_memory_client.

The openmemory extraction pipeline paraphrased saved memories into third-person
narration and stripped `[Project]:` prefixes because no fact-extraction prompt
was set unless the user configured custom_instructions. These tests pin the
fallback chain: custom_instructions param > DB custom_instructions > DEFAULT.
"""

from unittest.mock import MagicMock, patch

from app.utils import memory as memory_module
from app.utils.memory import get_memory_client, reset_memory_client
from app.utils.prompts import DEFAULT_FACT_EXTRACTION_PROMPT


def _build_client_and_capture_config(monkeypatch, custom_instructions=None, db_instructions=None):
    """Run get_memory_client with mocked DB + Memory build; return captured config."""
    captured = {}

    def fake_from_config(config_dict):
        captured["config"] = config_dict
        return MagicMock()

    db = MagicMock()
    db_config = None
    if db_instructions is not None:
        db_config = MagicMock()
        db_config.value = {"openmemory": {"custom_instructions": db_instructions}}
    db.query.return_value.filter.return_value.first.return_value = db_config

    reset_memory_client()
    with patch.object(memory_module, "SessionLocal", return_value=db):
        with patch.object(memory_module.Memory, "from_config", side_effect=fake_from_config):
            client = get_memory_client(custom_instructions=custom_instructions)

    assert client is not None
    return captured["config"]


def test_default_prompt_applied_when_no_custom_instructions(monkeypatch):
    config = _build_client_and_capture_config(monkeypatch)
    assert config["custom_fact_extraction_prompt"] == DEFAULT_FACT_EXTRACTION_PROMPT


def test_db_custom_instructions_override_default(monkeypatch):
    config = _build_client_and_capture_config(monkeypatch, db_instructions="my custom prompt")
    assert config["custom_fact_extraction_prompt"] == "my custom prompt"


def test_param_custom_instructions_override_db(monkeypatch):
    config = _build_client_and_capture_config(
        monkeypatch, custom_instructions="param prompt", db_instructions="db prompt"
    )
    assert config["custom_fact_extraction_prompt"] == "param prompt"


def test_default_prompt_preserves_project_tag_contract():
    # The prompt must instruct verbatim tag preservation and the facts JSON contract.
    assert "[ProjectName]:" in DEFAULT_FACT_EXTRACTION_PROMPT or "project tag" in DEFAULT_FACT_EXTRACTION_PROMPT.lower()
    assert '"facts"' in DEFAULT_FACT_EXTRACTION_PROMPT


def test_default_prompt_classifies_untagged_scope():
    # The prompt must instruct auto-classification of untagged facts into [global]:
    # or a project scope, and forbid guessing project names.
    assert "[global]:" in DEFAULT_FACT_EXTRACTION_PROMPT
    assert "CLASSIFY UNTAGGED FACTS" in DEFAULT_FACT_EXTRACTION_PROMPT
    assert "never guess a project name" in DEFAULT_FACT_EXTRACTION_PROMPT
