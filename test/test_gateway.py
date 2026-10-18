import json

import httpx
import pytest

from repo_ranger.llm.gateway import AIGateway, GatewayError


@pytest.mark.anyio
async def test_openai_compatible_complete():
  def handler(request: httpx.Request) -> httpx.Response:
    assert request.url.path.endswith("/chat/completions")
    assert request.headers["authorization"] == "Bearer test-key"
    payload = json.loads(request.content)
    assert payload["model"] == "meta-llama/llama-3.3-70b"
    assert len(payload["messages"]) == 2
    assert payload["messages"][0]["role"] == "system"

    return httpx.Response(
        200,
        json={
            "choices": [{"message": {"content": "Hello from mock OpenRouter!"}}]
        },
    )

  client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
  gateway = AIGateway(
      model="meta-llama/llama-3.3-70b",
      base_url="https://openrouter.ai/api/v1",
      api_key="test-key",
      client=client,
  )

  reply = await gateway.complete(
      messages=[{"role": "user", "content": "hi"}],
      system_prompt="You are Repo Ranger.",
  )
  assert reply == "Hello from mock OpenRouter!"


@pytest.mark.anyio
async def test_openai_compatible_stream():
  def handler(request: httpx.Request) -> httpx.Response:
    sse_body = (
        'data: {"choices":[{"delta":{"content":"Hel"}}]}\n\n'
        'data: {"choices":[{"delta":{"content":"lo"}}]}\n\n'
        'data: {"choices":[{"delta":{"content":" world"}}]}\n\n'
        "data: [DONE]\n\n"
    )
    return httpx.Response(
        200,
        content=sse_body.encode("utf-8"),
        headers={"content-type": "text/event-stream"},
    )

  client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
  gateway = AIGateway(
      model="qwen2.5-coder",
      base_url="http://localhost:11434/v1",
      client=client,
  )

  deltas = []
  async for chunk in gateway.stream_complete(
      messages=[{"role": "user", "content": "hi"}]
  ):
    deltas.append(chunk)

  assert "".join(deltas) == "Hello world"


@pytest.mark.anyio
async def test_gemini_complete_and_stream():
  def handler(request: httpx.Request) -> httpx.Response:
    if "streamGenerateContent" in request.url.path:
      sse_body = (
          'data: {"candidates":[{"content":{"parts":[{"text":"Streamed"}]}}]}\n\n'
          'data: {"candidates":[{"content":{"parts":[{"text":" Gemini"}]}}]}\n\n'
      )
      return httpx.Response(
          200,
          content=sse_body.encode("utf-8"),
          headers={"content-type": "text/event-stream"},
      )
    return httpx.Response(
        200,
        json={"candidates": [{"content": {"parts": [{"text": "Gemini 2.0"}]}}]},
    )

  client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
  gateway = AIGateway(
      model="gemini-2.0-flash",
      api_key="AIzaSy_fake_google_key",
      client=client,
  )
  assert gateway.provider == "gemini"

  reply = await gateway.complete(messages=[{"role": "user", "content": "hello"}])
  assert reply == "Gemini 2.0"

  deltas = []
  async for chunk in gateway.stream_complete(
      messages=[{"role": "user", "content": "stream this"}]
  ):
    deltas.append(chunk)
  assert "".join(deltas) == "Streamed Gemini"


@pytest.mark.anyio
async def test_anthropic_complete_and_stream():
  def handler(request: httpx.Request) -> httpx.Response:
    assert request.headers["x-api-key"] == "sk-ant-test"
    if request.url.path == "/v1/messages":
      payload = json.loads(request.content)
      if payload.get("stream"):
        sse_body = (
            'data: {"type":"content_block_delta","delta":{"text":"Claude"}}\n\n'
            'data: {"type":"content_block_delta","delta":{"text":" 3.5"}}\n\n'
        )
        return httpx.Response(
            200,
            content=sse_body.encode("utf-8"),
            headers={"content-type": "text/event-stream"},
        )
      return httpx.Response(
          200,
          json={"content": [{"type": "text", "text": "Claude 3.5 Sonnet"}]},
      )
    return httpx.Response(404)

  client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
  gateway = AIGateway(
      model="claude-3-5-sonnet",
      api_key="sk-ant-test",
      client=client,
  )
  assert gateway.provider == "anthropic"

  reply = await gateway.complete(
      messages=[{"role": "user", "content": "hi"}],
      system_prompt="Be concise",
  )
  assert reply == "Claude 3.5 Sonnet"

  streamed = []
  async for delta in gateway.stream_complete(
      messages=[{"role": "user", "content": "hi"}]
  ):
    streamed.append(delta)
  assert "".join(streamed) == "Claude 3.5"


@pytest.mark.anyio
async def test_error_handling_401():
  def handler(request: httpx.Request) -> httpx.Response:
    return httpx.Response(401, text="Unauthorized API key")

  client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
  gateway = AIGateway(
      model="test-model",
      base_url="https://api.openai.com/v1",
      api_key="bad-key",
      client=client,
  )

  with pytest.raises(GatewayError) as exc_info:
    await gateway.complete(messages=[{"role": "user", "content": "hi"}])

  assert exc_info.value.status_code == 401
  assert "Unauthorized" in str(exc_info.value)


def test_byom_requires_explicit_model_and_base_url():
  with pytest.raises(ValueError, match="model must be specified"):
    AIGateway(model="", base_url="http://localhost:11434/v1")

  with pytest.raises(ValueError, match="base_url must be specified"):
    AIGateway(model="my-model", provider="openai")

