import json
import os
from collections.abc import AsyncIterator
from typing import Any

import httpx


class GatewayError(Exception):

  def __init__(
      self, message: str, status_code: int = 500, body: str | None = None
  ):
    super().__init__(message)
    self.status_code = status_code
    self.body = body


class AIGateway:

  def __init__(
      self,
      model: str,
      base_url: str | None = None,
      api_key: str | None = None,
      provider: str | None = None,
      timeout: float = 60.0,
      client: httpx.AsyncClient | None = None,
  ):
    if not model or not model.strip():
      raise ValueError("model must be specified. Repo Ranger is BYOM.")

    self.model = model.strip()
    self.api_key = api_key
    self.timeout = timeout
    self._owned_client = client is None
    self._client = client or httpx.AsyncClient(timeout=timeout)

    if provider:
      self.provider = provider.lower().strip()
    elif api_key and api_key.startswith("AIzaSy"):
      self.provider = "gemini"
    elif api_key and api_key.startswith("sk-ant-"):
      self.provider = "anthropic"
    else:
      self.provider = "openai"

    if base_url and base_url.strip():
      self.base_url = base_url.rstrip("/")
    elif self.provider == "gemini":
      self.base_url = "https://generativelanguage.googleapis.com/v1beta"
    elif self.provider == "anthropic":
      self.base_url = "https://api.anthropic.com/v1"
    else:
      env_url = os.environ.get("OPENAI_BASE_URL")
      if env_url:
        self.base_url = env_url.rstrip("/")
      else:
        raise ValueError(
            "base_url must be specified for OpenAI-compatible endpoints"
            " (or set OPENAI_BASE_URL)."
        )

  async def __aenter__(self):
    return self

  async def __aexit__(self, exc_type, exc_val, exc_tb):
    await self.close()

  async def close(self):
    if self._owned_client:
      await self._client.aclose()

  async def complete(
      self,
      messages: list[dict[str, str]],
      system_prompt: str = "",
      temperature: float = 0.2,
      max_tokens: int = 2048,
  ) -> str:
    url, headers, payload = self._build_request(
        messages=messages,
        system_prompt=system_prompt,
        temperature=temperature,
        max_tokens=max_tokens,
        stream=False,
    )
    resp = await self._client.post(url, headers=headers, json=payload)
    if resp.status_code >= 400:
      raise GatewayError(
          f"API request failed with status {resp.status_code}: {resp.text}",
          status_code=resp.status_code,
          body=resp.text,
      )
    data = resp.json()
    return self._parse_completion(data)

  async def stream_complete(
      self,
      messages: list[dict[str, str]],
      system_prompt: str = "",
      temperature: float = 0.2,
      max_tokens: int = 2048,
  ) -> AsyncIterator[str]:
    url, headers, payload = self._build_request(
        messages=messages,
        system_prompt=system_prompt,
        temperature=temperature,
        max_tokens=max_tokens,
        stream=True,
    )
    async with self._client.stream(
        "POST", url, headers=headers, json=payload
    ) as resp:
      if resp.status_code >= 400:
        body = await resp.aread()
        raise GatewayError(
            f"API stream failed with status {resp.status_code}: {body.decode('utf-8', errors='replace')}",
            status_code=resp.status_code,
            body=body.decode("utf-8", errors="replace"),
        )
      async for line in resp.aiter_lines():
        line = line.strip()
        if not line:
          continue
        delta = self._parse_stream_line(line)
        if delta:
          yield delta

  def _build_request(
      self,
      messages: list[dict[str, str]],
      system_prompt: str,
      temperature: float,
      max_tokens: int,
      stream: bool,
  ) -> tuple[str, dict[str, str], dict[str, Any]]:
    if self.provider == "gemini":
      endpoint = (
          "streamGenerateContent?alt=sse" if stream else "generateContent"
      )
      url = f"{self.base_url}/models/{self.model}:{endpoint}"
      if self.api_key:
        url = (
            f"{url}&key={self.api_key}"
            if "?" in url
            else f"{url}?key={self.api_key}"
        )
      headers = {"Content-Type": "application/json"}
      contents = []
      for m in messages:
        role = "user" if m.get("role") == "user" else "model"
        contents.append(
            {"role": role, "parts": [{"text": m.get("content", "")}]}
        )
      payload: dict[str, Any] = {
          "contents": contents,
          "generationConfig": {
              "temperature": temperature,
              "maxOutputTokens": max_tokens,
          },
      }
      if system_prompt:
        payload["systemInstruction"] = {"parts": [{"text": system_prompt}]}
      return url, headers, payload

    if self.provider == "anthropic":
      url = f"{self.base_url}/messages"
      headers = {
          "Content-Type": "application/json",
          "anthropic-version": "2023-06-01",
      }
      if self.api_key:
        headers["x-api-key"] = self.api_key
      filtered_messages = [
          {"role": m["role"], "content": m["content"]}
          for m in messages
          if m.get("role") in ("user", "assistant")
      ]
      payload = {
          "model": self.model,
          "messages": filtered_messages,
          "temperature": temperature,
          "max_tokens": max_tokens,
          "stream": stream,
      }
      if system_prompt:
        payload["system"] = system_prompt
      return url, headers, payload

    url = f"{self.base_url}/chat/completions"
    headers = {"Content-Type": "application/json"}
    if self.api_key:
      headers["Authorization"] = f"Bearer {self.api_key}"
    all_messages = []
    if system_prompt:
      all_messages.append({"role": "system", "content": system_prompt})
    all_messages.extend(messages)
    payload = {
        "model": self.model,
        "messages": all_messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": stream,
    }
    return url, headers, payload

  def _parse_completion(self, data: dict[str, Any]) -> str:
    if self.provider == "gemini":
      candidates = data.get("candidates", [])
      if not candidates:
        return ""
      parts = candidates[0].get("content", {}).get("parts", [])
      return "".join(p.get("text", "") for p in parts)

    if self.provider == "anthropic":
      content = data.get("content", [])
      return "".join(
          c.get("text", "") for c in content if c.get("type") == "text"
      )

    choices = data.get("choices", [])
    if not choices:
      return ""
    return choices[0].get("message", {}).get("content", "") or ""

  def _parse_stream_line(self, line: str) -> str | None:
    if not line.startswith("data:"):
      return None
    raw = line[5:].strip()
    if raw == "[DONE]":
      return None
    try:
      data = json.loads(raw)
    except json.JSONDecodeError:
      return None

    if self.provider == "gemini":
      candidates = data.get("candidates", [])
      if candidates:
        parts = candidates[0].get("content", {}).get("parts", [])
        return "".join(p.get("text", "") for p in parts)
      return None

    if self.provider == "anthropic":
      event_type = data.get("type")
      if event_type == "content_block_delta":
        return data.get("delta", {}).get("text", "")
      return None

    choices = data.get("choices", [])
    if choices:
      return choices[0].get("delta", {}).get("content", "")
    return None
