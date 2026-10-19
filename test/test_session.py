import httpx
import pytest

from repo_ranger.llm.budget import ContextBudget, SecurityViolationError
from repo_ranger.llm.gateway import AIGateway
from repo_ranger.session import RepoSession


@pytest.fixture
def mock_gateway():
  def handler(request: httpx.Request) -> httpx.Response:
    import json

    payload = json.loads(request.content)
    if payload.get("stream"):
      sse = (
          'data: {"choices":[{"delta":{"content":"Token 1 "}}]}\n\n'
          'data: {"choices":[{"delta":{"content":"Token 2"}}]}\n\n'
          "data: [DONE]\n\n"
      )
      return httpx.Response(
          200,
          content=sse.encode("utf-8"),
          headers={"content-type": "text/event-stream"},
      )
    return httpx.Response(
        200,
        json={"choices": [{"message": {"content": "The answer is 42."}}]},
    )

  client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
  return AIGateway(
      model="test-coder",
      base_url="http://localhost:11434/v1",
      client=client,
  )


def test_session_airgap_guard():
  remote_client = httpx.AsyncClient(
      transport=httpx.MockTransport(lambda r: httpx.Response(200))
  )
  remote_gateway = AIGateway(
      model="remote-model",
      base_url="https://api.openai.com/v1",
      api_key="sk-test",
      client=remote_client,
  )
  budget = ContextBudget(max_context_tokens=4096)

  with pytest.raises(SecurityViolationError):
    RepoSession(
        gateway=remote_gateway,
        budget=budget,
        origin_url="git@github.com:myorg/secret.git",
        strict_local=True,
    )


def test_session_ingestion_and_search(tmp_path, mock_gateway):
  budget = ContextBudget(max_context_tokens=4096)
  session = RepoSession(
      gateway=mock_gateway,
      budget=budget,
      cache_dir=str(tmp_path / "cache"),
  )

  files = [
      ("auth.rs", "fn authenticate(user: str) -> bool { true }"),
      (
          "main.rs",
          (
              'fn main() { let ok = authenticate("alice");'
              ' println!("{}", ok); }'
          ),
      ),
  ]

  session.ingest_files(files)
  assert session.get_merkle_root() != ""
  assert "fn authenticate" in session.skeleton

  hits = session.search("authenticate")
  assert len(hits) >= 1
  assert any(h["file_path"] == "auth.rs" for h in hits)
  assert "auth.rs" in session.get_working_set()


@pytest.mark.anyio
async def test_session_ask_and_stream(tmp_path, mock_gateway):
  budget = ContextBudget(max_context_tokens=4096)
  session = RepoSession(
      gateway=mock_gateway,
      budget=budget,
      cache_dir=str(tmp_path / "cache"),
  )

  files = [
      ("calc.rs", "fn compute_total(a: i32, b: i32) -> i32 { a + b }"),
  ]
  session.ingest_files(files)

  reply = await session.ask("What does compute_total do?")
  assert reply == "The answer is 42."
  assert len(session.history) == 2
  assert session.history[0]["role"] == "user"
  assert session.history[1]["role"] == "assistant"

  streamed = []
  async for chunk in session.stream_ask("Can you stream it?"):
    streamed.append(chunk)

  assert "".join(streamed) == "Token 1 Token 2"
  assert len(session.history) == 4
