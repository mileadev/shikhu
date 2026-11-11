"""Offline integration tests for provider routing, provenance and privacy boundaries."""

from unittest.mock import MagicMock

import pytest

from shikhu import generator, inquiry, providers, systemone
from shikhu.commands.utils import ensure_api_key


def test_local_generation_without_openrouter_credentials(monkeypatch):
    monkeypatch.setenv("SHIKHU_PROVIDER", "ollama_local")
    monkeypatch.setenv("SHIKHU_MODEL", "qwen3:14b")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    call = MagicMock(return_value=(
        '{"questions":[{"question":"Why?","choices":["A","B","C","D"],"correct_index":0}]}',
        {"model": "qwen3:14b", "elapsed": 0.1, "cost": None},
    ))
    monkeypatch.setattr(providers, "chat", call)
    ensure_api_key()
    quiz, stats = generator.generate_quiz("Prompt")
    assert quiz.questions[0].question == "Why?"
    assert stats["cost"] is None
    assert call.call_args.kwargs["response_format"]["type"] == "json_schema"


def test_local_judgments_have_distinct_provenance(monkeypatch):
    monkeypatch.setenv("SHIKHU_PROVIDER", "ollama_local")
    monkeypatch.setenv("SHIKHU_MODEL", "qwen3:14b")
    monkeypatch.setattr(providers, "chat", lambda *a, **k: (
        '{"scores":{"gate":0.75}}',
        {"model": "qwen3:14b", "elapsed": 0.1, "cost": None},
    ))
    answers, stats = systemone.ask(
        state={"question": "how does this work?"},
        questions={"gate": systemone.noul("Is this about the code?")},
    )
    assert answers["gate"]["noul"] == pytest.approx(0.75)
    assert stats["judgment_kind"] == "uncalibrated_heuristic"
    assert inquiry.map_algo_version() != inquiry.MAP_ALGO_VERSION
    assert "ollama_local/qwen3:14b" in inquiry.map_algo_version()
    assert inquiry.past_question_bar()["algo_version"] == inquiry.map_algo_version()


def test_default_openrouter_provenance_unchanged(monkeypatch):
    monkeypatch.delenv("SHIKHU_PROVIDER", raising=False)
    assert inquiry.map_algo_version() == inquiry.MAP_ALGO_VERSION


def test_heuristic_batching(monkeypatch):
    monkeypatch.setenv("SHIKHU_PROVIDER", "ollama_local")
    files = {f"file{i}.py": "summary" for i in range(42)}
    assert [len(b) for b in inquiry._batches(files, inquiry.BATCH_FILES)] == [20, 20, 2]
    monkeypatch.setenv("SHIKHU_HEURISTIC_BATCH_FILES", "10")
    assert [len(b) for b in inquiry._batches(files, inquiry.BATCH_FILES)] == [10, 10, 10, 10, 2]


def test_symlinked_source_cannot_be_loaded(tmp_path):
    from shikhu.store import read_file_lines

    target = tmp_path / "private.txt"
    target.write_text("private-content")
    link = tmp_path / "public.py"
    link.symlink_to(target)
    assert read_file_lines(str(link)) is None


def test_save_key_does_not_follow_symlinks(tmp_path, monkeypatch):
    from shikhu import env

    target = tmp_path / "elsewhere"
    target.write_text("do-not-change")
    folder = tmp_path / "shikhu"
    folder.mkdir()
    (folder / ".env").symlink_to(target)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    with pytest.raises(RuntimeError, match="symlink"):
        env.save_key("secret")
    assert target.read_text() == "do-not-change"
