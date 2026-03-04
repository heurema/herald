"""Herald v2 CLI entry point.

Subcommands: init, run, brief, status
Data directory: ~/.herald/ (override via --data-dir flag or HERALD_DATA_DIR env var)
--data-dir flag takes precedence over HERALD_DATA_DIR env var.
"""
from __future__ import annotations

import argparse
import datetime
import os
import sys
from pathlib import Path

from herald.config import load_config
from herald.db import Database
from herald.pipeline import run_pipeline
from herald.project import project_brief


DEFAULT_DATA_DIR = Path.home() / ".herald"

DEFAULT_CONFIG_TEMPLATE = """\
# Herald configuration
# Add sources below. Example:
# sources:
#   - id: hn
#     name: Hacker News
#     weight: 0.3
#     category: community

sources: []

clustering:
  threshold: 0.65
  max_time_gap_days: 7

schedule:
  interval_hours: 4
"""


def _resolve_data_dir(args: argparse.Namespace) -> Path:
    """Return data_dir: --data-dir flag > HERALD_DATA_DIR env var > ~/.herald/"""
    if args.data_dir is not None:
        return Path(args.data_dir)
    env = os.environ.get("HERALD_DATA_DIR")
    if env:
        return Path(env)
    return DEFAULT_DATA_DIR


def cmd_init(args: argparse.Namespace) -> int:
    data_dir = _resolve_data_dir(args)
    data_dir.mkdir(parents=True, exist_ok=True)

    config_path = data_dir / "config.yaml"
    if not config_path.exists():
        config_path.write_text(DEFAULT_CONFIG_TEMPLATE, encoding="utf-8")

    db_path = data_dir / "herald.db"
    try:
        db = Database(db_path)
        db.close()
    except Exception as exc:
        print(f"Error initializing database: {exc}", file=sys.stderr)
        return 1

    print(f"Initialized Herald data directory: {data_dir}")
    print(f"Config: {config_path}")
    print(f"Database: {db_path}")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    data_dir = _resolve_data_dir(args)
    config_path = data_dir / "config.yaml"

    if not data_dir.exists():
        print(
            f"Error: data directory not found: {data_dir}\n"
            "Run 'herald init' first.",
            file=sys.stderr,
        )
        return 1

    if not config_path.exists():
        print(
            f"Error: config file not found: {config_path}\n"
            "Run 'herald init' to create a default configuration.",
            file=sys.stderr,
        )
        return 1

    try:
        config = load_config(config_path)
        db_path = data_dir / "herald.db"
        db = Database(db_path)
        try:
            adapter_map = {s.id: s.type for s in config.sources}
            result = run_pipeline(config, db, adapter_map=adapter_map, data_dir=data_dir)
        finally:
            db.close()

        brief_path = data_dir / "briefs" / f"{result.run_id}.md"
        print(f"Pipeline complete. Brief: {brief_path}")
        return 0

    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Error running pipeline: {exc}", file=sys.stderr)
        return 1


def cmd_brief(args: argparse.Namespace) -> int:
    data_dir = _resolve_data_dir(args)
    db_path = data_dir / "herald.db"

    if not db_path.exists():
        print(
            f"Error: database not found: {db_path}\n"
            "Run 'herald init' and 'herald run' first.",
            file=sys.stderr,
        )
        return 1

    try:
        db = Database(db_path)
        try:
            brief = project_brief(db)
        finally:
            db.close()

        print(brief, end="")
        return 0

    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Error generating brief: {exc}", file=sys.stderr)
        return 1


def cmd_status(args: argparse.Namespace) -> int:
    data_dir = _resolve_data_dir(args)
    db_path = data_dir / "herald.db"

    if not db_path.exists():
        print(
            f"Error: database not found: {db_path}\n"
            "Run 'herald init' first.",
            file=sys.stderr,
        )
        return 1

    try:
        db = Database(db_path)
        try:
            article_count = db.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
            story_count = db.execute(
                "SELECT COUNT(*) FROM stories WHERE status = 'active'"
            ).fetchone()[0]
            last_run_row = db.execute(
                "SELECT finished_at FROM pipeline_runs ORDER BY id DESC LIMIT 1"
            ).fetchone()
        finally:
            db.close()

        last_run = "never"
        if last_run_row is not None and last_run_row[0] is not None:
            ts = last_run_row[0]
            last_run = datetime.datetime.fromtimestamp(
                ts, tz=datetime.timezone.utc
            ).strftime("%Y-%m-%dT%H:%M:%SZ")

        print(f"Articles: {article_count}")
        print(f"Stories:  {story_count}")
        print(f"Last run: {last_run}")
        return 0

    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Error reading status: {exc}", file=sys.stderr)
        return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="herald",
        description="Herald v2 — daily curated news digest",
    )
    parser.add_argument(
        "--data-dir",
        metavar="DIR",
        default=None,
        help="Data directory (default: ~/.herald/ or HERALD_DATA_DIR env var)",
    )

    subparsers = parser.add_subparsers(dest="command", metavar="COMMAND")

    subparsers.add_parser("init", help="Initialize data directory and database")
    subparsers.add_parser("run", help="Run the collection pipeline")
    subparsers.add_parser("brief", help="Print latest brief to stdout")
    subparsers.add_parser("status", help="Show database statistics")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return 0

    commands = {
        "init": cmd_init,
        "run": cmd_run,
        "brief": cmd_brief,
        "status": cmd_status,
    }
    return commands[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
