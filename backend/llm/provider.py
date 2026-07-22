from litellm import acompletion, completion_cost, token_counter
from litellm.exceptions import (
    AuthenticationError,
    ContextWindowExceededError,
    RateLimitError,
)
from litellm.types.utils import ModelResponse

SCOPE_SYSTEM_PROMPT = """You are Repo Ranger, you analyze and explain github repositories
for young programmers to learn easily and for all programmers to help in contributing to open source
You answer ONLY based on the code and dependencies and documentation of the code
and of said dependencies.
Unless specifically prompted for assistance in improvement/contribution/comparison, you DO NOT use
external knowledge about libraries, frameworks, or tools and APIs.
Cite the specific filename for each claim.
Answer as if u are that repository"""


class LLMProvider:
    def __init__(self, provider: str, api_key: str, model: str | None = None):

        self.provider = provider
        self.api_key = api_key

        if provider == "local":
            if model:
                self.model = model if model.startswith("ollama/") else f"ollama/{model}"
            else:
                raise ValueError("model is required for local provider")
        elif model:
            self.model = model
        elif provider == "openai":
            self.model = "gpt-4o"
        elif provider == "anthropic":
            self.model = "claude-sonnet-4-5-20250929"
        elif provider == "google":
            self.model = "gemini/gemini-2.0-flash-exp"
        else:
            raise ValueError(
                f"""Unsupported provider: '{provider}'. \n
                Supported providers are: local, openai, anthropic, google"""
            )

    async def generate(self, question: str, context: str) -> str:

        kwargs = {}
        if self.provider == "local":
            kwargs["api_base"] = "http://localhost:11434"
        else:
            kwargs["api_key"] = self.api_key

        try:
            resp = await acompletion(
                model=self.model,
                messages=[
                    {"role": "system", "content": SCOPE_SYSTEM_PROMPT},
                    {"role": "user", "content": f"{context}\n\nQuestion: {question}"},
                ],
                stream=False,
                **kwargs,
            )
            assert isinstance(resp, ModelResponse)
            content = resp.choices[0].message.content
            if content is None:
                raise ValueError("LLM returned empty response")
            return content

        except AuthenticationError:
            raise ValueError("Invalid API key")
        except RateLimitError:
            raise ValueError("Rate limit by provider exceeded")
        except ContextWindowExceededError:
            raise ValueError("Context too long for this model")
        except Exception as e:
            raise ValueError(f"provider error: {e}")

    async def generate_stream(self, question: str, context: str):
        """Yield content chunks as they arrive from the LLM."""
        kwargs = {}
        if self.provider == "local":
            kwargs["api_base"] = "http://localhost:11434"
        else:
            kwargs["api_key"] = self.api_key

        try:
            resp = await acompletion(
                model=self.model,
                messages=[
                    {"role": "system", "content": SCOPE_SYSTEM_PROMPT},
                    {"role": "user", "content": f"{context}\n\nQuestion: {question}"},
                ],
                stream=True,
                **kwargs,
            )
            async for chunk in resp:
                delta = chunk.choices[0].delta.content
                if delta:
                    yield delta
        except AuthenticationError:
            raise ValueError("Invalid API key")
        except RateLimitError:
            raise ValueError("Rate limit by provider exceeded")
        except ContextWindowExceededError:
            raise ValueError("Context too long for this model")
        except Exception as e:
            raise ValueError(f"provider error: {e}")

    def get_cost(self, resp) -> float | None:
        try:
            return completion_cost(completion_response=resp)
        except Exception:
            return None

    def count_tokens(self, text: str) -> int:
        return token_counter(model=self.model, text=text)
