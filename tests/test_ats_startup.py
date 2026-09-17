from contextlib import nullcontext
from unittest.mock import Mock

import pytest

import app
import cli
from services.ats_status import get_ats_status


@pytest.mark.parametrize(
    ("arguments", "handler", "skips"),
    [
        (["collect", "--skip", "ashby", "invalid"], "_collect_all", ["ashby", "invalid"]),
        (["collect", "watchlist", "--skip-ats", "lever"], "_collect_watchlist", ["lever"]),
        # --skip here names company slugs, not ATS types.
        (["collect", "ats", "ashby", "--skip", "lever"], "_collect_ats", []),
        (["collect", "company", "openai"], "_collect_company", []),
        (["database"], "_database", []),
    ],
)
def test_cli_logs_before_command(monkeypatch, arguments, handler, skips):
    info = Mock()
    monkeypatch.setattr("services.ats_status.logger.info", info)
    monkeypatch.setattr("sys.argv", ["openats", *arguments])

    def command(args):
        info.assert_called_once_with(operation="ats_status", **get_ats_status(skips))

    command_mock = Mock(side_effect=command)
    monkeypatch.setattr(cli, handler, command_mock)
    cli.main()
    command_mock.assert_called_once()


@pytest.mark.parametrize("arguments", [[], ["collect"], None])
def test_continuous_startup_logs_once_before_database(monkeypatch, arguments):
    info = Mock()
    monkeypatch.setattr("services.ats_status.logger.info", info)
    monkeypatch.setattr(app.os.path, "exists", lambda path: False)
    monkeypatch.setattr(app.os.path, "isdir", lambda path: False)
    monkeypatch.setattr(app.os, "remove", Mock())
    monkeypatch.setattr(app.shutil, "rmtree", Mock())

    def connect():
        status_events = [
            call for call in info.call_args_list if call.kwargs["operation"] == "ats_status"
        ]
        assert len(status_events) == 1
        assert status_events[0].kwargs == {"operation": "ats_status", **get_ats_status()}
        return nullcontext(Mock())

    monkeypatch.setattr(app.database, "connect", connect)
    monkeypatch.setattr(app.database, "read_companies_ats", lambda connection: {})
    monkeypatch.setattr(app.database, "read_companies_no_ats", lambda connection: [])
    pipeline = Mock(side_effect=[("success", 0, 0), ("cancelled", 0, 0)])
    monkeypatch.setattr(app, "_run_collect_pipeline", pipeline)

    if arguments is None:
        app.main()
    else:
        monkeypatch.setattr("sys.argv", ["openats", *arguments])
        cli.main()
    assert pipeline.call_count == 2


def test_watchlist_excludes_globally_disabled_ats(monkeypatch):
    connection = Mock()
    connection.execute.return_value.fetchall.return_value = []
    monkeypatch.setattr(cli.database, "connect", lambda: nullcontext(connection))
    monkeypatch.setattr(
        cli.database,
        "read_watchlists",
        lambda connection: [
            {"ats": ats, "company_slug": ats, "company_name": ats}
            for ats in ["ashby", "eures", "lever"]
        ],
    )
    pipeline = Mock(return_value=("success", 0, 0))
    monkeypatch.setattr(cli, "_run_collect_pipeline", pipeline)
    args = cli._build_parser().parse_args(["collect", "watchlist", "--skip-ats", "lever"])

    cli._collect_watchlist(args)

    assert list(pipeline.call_args.args[0]) == ["ashby"]
