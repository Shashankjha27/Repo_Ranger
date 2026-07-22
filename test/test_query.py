from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)


# ── request validation ────────────────────────────────────────────


def test_query_missing_question():
    response = client.post(
        "/query",
        json={
            "github_url": "https://github.com/octocat/hello-world",
            "provider": "openai",
            "api_key": "sk-test",
        },
    )
    assert response.status_code == 422


def test_query_missing_api_key():
    response = client.post(
        "/query",
        json={
            "question": "What is this repo?",
            "github_url": "https://github.com/octocat/hello-world",
            "provider": "openai",
        },
    )
    assert response.status_code == 422


def test_query_bad_url():
    response = client.post(
        "/query",
        json={
            "question": "What is this?",
            "github_url": "not-a-url",
            "provider": "openai",
            "api_key": "sk-test",
        },
    )
    assert response.status_code == 400


def test_query_empty_question():
    response = client.post(
        "/query",
        json={
            "question": "",
            "github_url": "https://github.com/octocat/hello-world",
            "provider": "openai",
            "api_key": "sk-test",
        },
    )
    assert response.status_code == 400


# ── full pipeline with mocks ─────────────────────────────────────


def _make_mock_repo_data():
    """Build a minimal RepoData-like object for mocking."""
    mock = MagicMock()
    mock.files = [
        {
            "path": "main.py",
            "relative_path": "main.py",
            "content": "def hello():\n    print('hi')\n",
            "file_type": ".py",
            "size_bytes": 40,
        },
        {
            "path": "requirements.txt",
            "relative_path": "requirements.txt",
            "content": "flask>=2.0\n",
            "file_type": ".txt",
            "size_bytes": 14,
        },
    ]
    return mock


@patch("backend.main.LLMProvider")
@patch("backend.main.fetch_repo")
def test_query_returns_answer(mock_fetch, mock_provider_cls):
    mock_fetch.return_value = _make_mock_repo_data()

    mock_provider = MagicMock()
    mock_provider.generate = AsyncMock(return_value="This repo has a hello function.")
    mock_provider.model = "gpt-4o"
    mock_provider_cls.return_value = mock_provider

    response = client.post(
        "/query",
        json={
            "question": "What does this repo do?",
            "github_url": "https://github.com/octocat/hello-world",
            "provider": "openai",
            "api_key": "sk-test",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert "answer" in data
    assert data["answer"] == "This repo has a hello function."
    mock_provider.generate.assert_called_once()


@patch("backend.main.LLMProvider")
@patch("backend.main.fetch_repo")
def test_query_passes_context_to_llm(mock_fetch, mock_provider_cls):
    mock_fetch.return_value = _make_mock_repo_data()

    mock_provider = MagicMock()
    mock_provider.generate = AsyncMock(return_value="answer")
    mock_provider.model = "gpt-4o"
    mock_provider_cls.return_value = mock_provider

    client.post(
        "/query",
        json={
            "question": "What is this?",
            "github_url": "https://github.com/octocat/hello-world",
            "provider": "openai",
            "api_key": "sk-test",
        },
    )

    call_args = mock_provider.generate.call_args
    question_arg = call_args[0][0]
    context_arg = call_args[0][1]
    assert question_arg == "What is this?"
    assert "Repository: octocat/hello-world" in context_arg
    assert "flask" in context_arg


@patch("backend.main.LLMProvider")
@patch("backend.main.fetch_repo")
def test_query_llm_error_returns_400(mock_fetch, mock_provider_cls):
    mock_fetch.return_value = _make_mock_repo_data()

    mock_provider = MagicMock()
    mock_provider.generate = AsyncMock(side_effect=ValueError("Invalid API key"))
    mock_provider.model = "gpt-4o"
    mock_provider_cls.return_value = mock_provider

    response = client.post(
        "/query",
        json={
            "question": "What is this?",
            "github_url": "https://github.com/octocat/hello-world",
            "provider": "openai",
            "api_key": "sk-bad",
        },
    )

    assert response.status_code == 400
    assert "Invalid API key" in response.json()["detail"]


@patch("backend.main.LLMProvider")
@patch("backend.main.fetch_repo")
def test_stream_returns_chunks(mock_fetch, mock_provider_cls):
    mock_fetch.return_value = _make_mock_repo_data()

    async def _mock_stream():
        for chunk in ["Hello", "World"]:
            yield chunk

    mock_provider = MagicMock()
    mock_provider.generate_stream = MagicMock(return_value=_mock_stream())
    mock_provider.model = "gpt-4o"
    mock_provider_cls.return_value = mock_provider

    response = client.post(
        "/query/stream",
        json={
            "question": "What does this repo do?",
            "github_url": "https://github.com/octocat/hello-world",
            "provider": "openai",
            "api_key": "sk-test",
        },
    )

    assert response.status_code == 200
    assert "text/event-stream" in response.headers["Content-Type"]
    lines = [
        line for line in response.text.strip().split("\n") if line.startswith("data: ")
    ]
    assert lines[0] == "data: Hello"
    assert lines[1] == "data: World"
    assert lines[-1] == "data: [DONE]"


def test_stream_bad_url():
    response = client.post(
        "/query/stream",
        json={
            "question": "What is this?",
            "github_url": "not-a-url",
            "provider": "openai",
            "api_key": "sk-test",
        },
    )
    assert response.status_code == 400


def test_stream_missing_question():
    response = client.post(
        "/query/stream",
        json={
            "github_url": "https://github.com/octocat/hello-world",
            "provider": "openai",
            "api_key": "sk-test",
        },
    )
    assert response.status_code == 422


def test_stream_empty_question():
    response = client.post(
        "/query/stream",
        json={
            "question": "",
            "github_url": "https://github.com/octocat/hello-world",
            "provider": "openai",
            "api_key": "sk-test",
        },
    )
    assert response.status_code == 400


def test_stream_missing_api_key():
    response = client.post(
        "/query/stream",
        json={
            "question": "What is this?",
            "github_url": "https://github.com/octocat/hello-world",
            "provider": "openai",
        },
    )
    assert response.status_code == 422


@patch("backend.main.LLMProvider")
@patch("backend.main.fetch_repo")
def test_stream_context_passed_to_llm(mock_fetch, mock_provider_cls):
    mock_fetch.return_value = _make_mock_repo_data()

    async def _mock_stream():
        yield "ok"

    mock_provider = MagicMock()
    mock_provider.generate_stream = MagicMock(return_value=_mock_stream())
    mock_provider.model = "gpt-4o"
    mock_provider_cls.return_value = mock_provider

    client.post(
        "/query/stream",
        json={
            "question": "What is this?",
            "github_url": "https://github.com/octocat/hello-world",
            "provider": "openai",
            "api_key": "sk-test",
        },
    )

    call_args = mock_provider.generate_stream.call_args
    question_arg = call_args[0][0]
    context_arg = call_args[0][1]
    assert question_arg == "What is this?"
    assert "Repository: octocat/hello-world" in context_arg
    assert "flask" in context_arg


@patch("backend.main.LLMProvider")
@patch("backend.main.fetch_repo")
def test_stream_llm_error_in_sse(mock_fetch, mock_provider_cls):
    mock_fetch.return_value = _make_mock_repo_data()

    async def _mock_stream_error():
        raise ValueError("Invalid API Key")
        yield  # noqa: F841

    mock_provider = MagicMock()
    mock_provider.generate_stream = MagicMock(return_value=_mock_stream_error())
    mock_provider.model = "gpt-4o"
    mock_provider_cls.return_value = mock_provider

    response = client.post(
        "/query/stream",
        json={
            "question": "What is this?",
            "github_url": "https://github.com/octocat/hello-world",
            "provider": "openai",
            "api_key": "sk-test",
        },
    )
    assert response.status_code == 200
    assert "[ERROR: Invalid API Key]" in response.text


@patch("backend.main.LLMProvider")
@patch("backend.main.fetch_repo")
def test_stream_ends_without_done_marker_after_error(mock_fetch, mock_provider_cls):
    mock_fetch.return_value = _make_mock_repo_data()

    async def _mock_stream_error():
        raise ValueError("Invalid API Key")
        yield  # noqa: F841

    mock_provider = MagicMock()
    mock_provider.generate_stream = MagicMock(return_value=_mock_stream_error())
    mock_provider.model = "gpt-4o"
    mock_provider_cls.return_value = mock_provider

    response = client.post(
        "/query/stream",
        json={
            "question": "What is this?",
            "github_url": "https://github.com/octocat/hello-world",
            "provider": "openai",
            "api_key": "sk-test",
        },
    )

    lines = [
        line for line in response.text.strip().split("\n") if line.startswith("data: ")
    ]
    assert lines[-1] != "data: [DONE]"
