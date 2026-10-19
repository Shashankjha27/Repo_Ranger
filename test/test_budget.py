import pytest

from repo_ranger.llm.budget import (
  ContextBudget,
  SecurityViolationError,
  assert_airgap_compliance,
  estimate_tokens,
  is_local_url,
  is_private_repo,
)


def test_token_estimation():
  assert estimate_tokens("") == 0
  assert estimate_tokens("abcd") == 1
  assert estimate_tokens("a" * 40) == 10


def test_byom_context_validation():
  with pytest.raises(ValueError, match="max_context_tokens must be positive"):
    ContextBudget(max_context_tokens=0)

  with pytest.raises(ValueError, match="max_context_tokens must be positive"):
    ContextBudget(max_context_tokens=-500)


def test_chunk_fitting_respects_budget():
  budget = ContextBudget(max_context_tokens=100, chunks_ratio=0.5)

  chunks = [
      {"file_path": "a.py", "content": "x" * 80},
      {"file_path": "b.py", "content": "y" * 80},
      {"file_path": "c.py", "content": "z" * 80},
  ]
  fitted = budget.fit_chunks(chunks)
  assert len(fitted) == 2
  assert fitted[0]["file_path"] == "a.py"
  assert fitted[1]["file_path"] == "b.py"


def test_history_pruning_removes_oldest():
  budget = ContextBudget(max_context_tokens=100, history_ratio=0.3)

  messages = [
      {"role": "user", "content": "turn 1: " + "a" * 50},
      {"role": "assistant", "content": "reply 1: " + "b" * 50},
      {"role": "user", "content": "turn 2: " + "c" * 50},
      {"role": "assistant", "content": "reply 2: " + "d" * 50},
  ]

  fitted = budget.fit_history(messages)
  assert len(fitted) < len(messages)
  assert fitted[-1]["role"] == "assistant"
  assert "reply 2" in fitted[-1]["content"]


def test_skeleton_truncation():
  budget = ContextBudget(max_context_tokens=100, skeleton_ratio=0.1)

  long_skeleton = "def func():\n    pass\n" * 20
  truncated = budget.truncate_skeleton(long_skeleton)
  assert len(truncated) < len(long_skeleton)
  assert estimate_tokens(truncated) <= 10


def test_build_prompt():
  budget = ContextBudget(max_context_tokens=1000)
  skeleton = "class Engine: pass"
  chunks = [{"file_path": "engine.py", "content": "def run(): return 42"}]
  history = [{"role": "user", "content": "prev query"}]
  query = "how does engine run?"

  prompt_messages = budget.build_prompt(
      skeleton=skeleton,
      chunks=chunks,
      history=history,
      query=query,
  )

  assert len(prompt_messages) >= 3
  assert prompt_messages[0]["role"] == "system"
  assert "class Engine: pass" in prompt_messages[0]["content"]
  assert "engine.py" in prompt_messages[0]["content"]
  assert prompt_messages[-1]["role"] == "user"
  assert prompt_messages[-1]["content"] == "how does engine run?"


def test_security_airgap_url_helpers():
  assert is_local_url("http://localhost:11434/v1")
  assert is_local_url("http://127.0.0.1:8000")
  assert not is_local_url("https://api.openai.com/v1")
  assert not is_local_url("https://openrouter.ai/api/v1")

  assert is_private_repo("git@github.com:myorg/secret.git")
  assert is_private_repo("ssh://git@internal.corp.com/repo.git")
  assert not is_private_repo("https://github.com/torvalds/linux.git")


def test_security_airgap_enforcement():
  assert_airgap_compliance(
      origin_url="git@github.com:org/private.git",
      base_url="http://localhost:11434/v1",
      strict_local=True,
  )

  with pytest.raises(SecurityViolationError):
    assert_airgap_compliance(
        origin_url="git@github.com:org/private.git",
        base_url="https://api.openai.com/v1",
        strict_local=True,
    )

  with pytest.raises(SecurityViolationError):
    assert_airgap_compliance(
        origin_url="https://github.com/public/repo.git",
        base_url="https://api.openai.com/v1",
        strict_local=True,
    )
