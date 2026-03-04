"""Tests for herald/cli.py — Herald v2 CLI entry point."""
from __future__ import annotations

import sys
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from herald.cli import build_parser, main, DEFAULT_CONFIG_TEMPLATE


# ---------------------------------------------------------------------------
# AC6: Argument parsing
# ---------------------------------------------------------------------------


def test_argument_parsing():
    parser = build_parser()

    # Default: no data_dir
    args = parser.parse_args(["init"])
    assert args.command == "init"
    assert args.data_dir is None

    # Explicit --data-dir
    args = parser.parse_args(["--data-dir", "/tmp/test", "run"])
    assert args.command == "run"
    assert args.data_dir == "/tmp/test"

    # All subcommands parse correctly
    for cmd in ("init", "run", "brief", "status"):
        args = parser.parse_args([cmd])
        assert args.command == cmd


# ---------------------------------------------------------------------------
# AC1: init creates data_dir, config.yaml, and database
# ---------------------------------------------------------------------------


def test_init_creates_data_dir(tmp_path):
    data_dir = tmp_path / "herald_data"
    assert not data_dir.exists()

    with patch("herald.cli.Database") as MockDB:
        mock_db = MagicMock()
        MockDB.return_value = mock_db

        exit_code = main(["--data-dir", str(data_dir), "init"])

    assert exit_code == 0
    assert data_dir.exists()

    config_path = data_dir / "config.yaml"
    assert config_path.exists()
    content = config_path.read_text(encoding="utf-8")
    assert "sources" in content

    # Database was instantiated with the correct path
    MockDB.assert_called_once_with(data_dir / "herald.db")
    mock_db.close.assert_called_once()


# ---------------------------------------------------------------------------
# AC2: init respects --data-dir flag and HERALD_DATA_DIR env var
# --data-dir flag takes precedence over env var
# ---------------------------------------------------------------------------


def test_init_respects_data_dir(tmp_path, monkeypatch):
    env_dir = tmp_path / "env_data"
    flag_dir = tmp_path / "flag_data"

    # HERALD_DATA_DIR set, but --data-dir flag overrides it
    monkeypatch.setenv("HERALD_DATA_DIR", str(env_dir))

    with patch("herald.cli.Database") as MockDB:
        MockDB.return_value = MagicMock()
        exit_code = main(["--data-dir", str(flag_dir), "init"])

    assert exit_code == 0
    assert flag_dir.exists()
    assert not env_dir.exists()

    # Without flag, env var is used
    with patch("herald.cli.Database") as MockDB:
        MockDB.return_value = MagicMock()
        exit_code = main(["init"])

    assert exit_code == 0
    assert env_dir.exists()


# ---------------------------------------------------------------------------
# AC3: run loads config, opens Database, calls run_pipeline, prints brief path
# ---------------------------------------------------------------------------


def test_run_executes_pipeline(tmp_path, capsys):
    data_dir = tmp_path / "herald"
    data_dir.mkdir()
    config_path = data_dir / "config.yaml"
    config_path.write_text("sources: []\n", encoding="utf-8")

    mock_config = MagicMock()
    mock_db = MagicMock()
    mock_result = MagicMock()
    mock_result.run_id = 42

    with (
        patch("herald.cli.load_config", return_value=mock_config) as mock_load,
        patch("herald.cli.Database", return_value=mock_db) as MockDB,
        patch("herald.cli.run_pipeline", return_value=mock_result) as mock_pipeline,
    ):
        exit_code = main(["--data-dir", str(data_dir), "run"])

    assert exit_code == 0

    mock_load.assert_called_once_with(config_path)
    MockDB.assert_called_once_with(data_dir / "herald.db")
    mock_pipeline.assert_called_once_with(mock_config, mock_db, data_dir=data_dir)
    mock_db.close.assert_called_once()

    captured = capsys.readouterr()
    assert "42" in captured.out
    assert "brief" in captured.out.lower() or "briefs" in captured.out.lower()


# ---------------------------------------------------------------------------
# AC4: brief opens Database, calls project_brief, prints to stdout
# ---------------------------------------------------------------------------


def test_brief_generates_output(tmp_path, capsys):
    data_dir = tmp_path / "herald"
    data_dir.mkdir()
    db_path = data_dir / "herald.db"

    # Create a real empty database so the file exists
    from herald.db import Database as RealDatabase
    real_db = RealDatabase(db_path)
    real_db.close()

    mock_db = MagicMock()
    mock_brief = "---\ngenerated_at: 2026-01-01T00:00:00Z\nstory_count: 0\n---\n"

    with (
        patch("herald.cli.Database", return_value=mock_db) as MockDB,
        patch("herald.cli.project_brief", return_value=mock_brief) as mock_proj,
    ):
        exit_code = main(["--data-dir", str(data_dir), "brief"])

    assert exit_code == 0
    MockDB.assert_called_once_with(db_path)
    mock_proj.assert_called_once_with(mock_db)
    mock_db.close.assert_called_once()

    captured = capsys.readouterr()
    assert mock_brief in captured.out


# ---------------------------------------------------------------------------
# AC5: status shows article count, story count, last pipeline run
# ---------------------------------------------------------------------------


def test_status_shows_db_stats(tmp_path, capsys):
    data_dir = tmp_path / "herald"
    data_dir.mkdir()
    db_path = data_dir / "herald.db"

    # Create a real database and populate it
    from herald.db import Database as RealDatabase

    db = RealDatabase(db_path)
    db.execute(
        "INSERT INTO sources (id, name, weight, category) VALUES ('s1', 'Test', 0.5, 'community')"
    )
    db.execute(
        """
        INSERT INTO articles
            (id, url_original, url_canonical, title, origin_source_id,
             collected_at, score_base, scored_at)
        VALUES
            ('a1', 'http://x.com/1', 'http://x.com/1', 'Title One', 's1',
             1000000, 0.5, 1000000)
        """
    )
    db.execute(
        "INSERT INTO pipeline_runs (started_at, finished_at) VALUES (1000000, 1000100)"
    )
    db.close()

    exit_code = main(["--data-dir", str(data_dir), "status"])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "Articles: 1" in captured.out
    assert "Stories:" in captured.out
    assert "Last run:" in captured.out
    # The finished_at timestamp (1000100) should be formatted, not "never"
    assert "never" not in captured.out


# ---------------------------------------------------------------------------
# AC7: error handling — missing config, missing data_dir
# ---------------------------------------------------------------------------


def test_run_error_missing_config(tmp_path, capsys):
    data_dir = tmp_path / "herald"
    data_dir.mkdir()
    # No config.yaml

    exit_code = main(["--data-dir", str(data_dir), "run"])

    assert exit_code != 0
    captured = capsys.readouterr()
    assert "config" in captured.err.lower() or "error" in captured.err.lower()


def test_run_error_missing_data_dir(tmp_path, capsys):
    data_dir = tmp_path / "nonexistent"
    # Directory does not exist

    exit_code = main(["--data-dir", str(data_dir), "run"])

    assert exit_code != 0
    captured = capsys.readouterr()
    assert captured.err.strip() != ""


def test_brief_error_missing_db(tmp_path, capsys):
    data_dir = tmp_path / "herald"
    data_dir.mkdir()
    # No database file

    exit_code = main(["--data-dir", str(data_dir), "brief"])

    assert exit_code != 0
    captured = capsys.readouterr()
    assert "error" in captured.err.lower()


def test_status_error_missing_db(tmp_path, capsys):
    data_dir = tmp_path / "herald"
    data_dir.mkdir()
    # No database file

    exit_code = main(["--data-dir", str(data_dir), "status"])

    assert exit_code != 0
    captured = capsys.readouterr()
    assert "error" in captured.err.lower()
