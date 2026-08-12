import json
from pathlib import Path

from click.testing import CliRunner

from chatpost.cli import main


def _registry(tmp_path: Path) -> Path:
    zhihu_runner = tmp_path / "zhihu-runner.toml"
    zhihu_runner.write_text("[zhihu]\n", encoding="utf-8")
    xhs_runner = tmp_path / "xhs-runner.toml"
    xhs_runner.write_text("[xhs]\n", encoding="utf-8")
    csdn_runner = tmp_path / "csdn-runner.toml"
    csdn_runner.write_text("[csdn]\n", encoding="utf-8")
    registry = tmp_path / "accounts.toml"
    registry.write_text(
        '[accounts."zhihu-test"]\n'
        'platform = "zhihu"\n'
        f'runner_config = {json.dumps(str(zhihu_runner))}\n'
        'profile = "zhihu-test"\n'
        'label = "Zhihu test account"\n',
        encoding="utf-8",
    )
    with registry.open("a", encoding="utf-8") as stream:
        stream.write(
            '\n[accounts."xhs-test"]\n'
            'platform = "xhs"\n'
            f'runner_config = {json.dumps(str(xhs_runner))}\n'
            'profile = "xhs-test"\n'
            'label = "XHS test account"\n'
            '\n[accounts."csdn-test"]\n'
            'platform = "csdn"\n'
            f'runner_config = {json.dumps(str(csdn_runner))}\n'
            'profile = "csdn-test"\n'
            'label = "CSDN test account"\n'
        )
    return registry


def _zhihu_registry(tmp_path: Path) -> Path:
    runner = tmp_path / "runner.toml"
    runner.write_text("[zhihu]\n", encoding="utf-8")
    registry = tmp_path / "accounts.toml"
    registry.write_text(
        '[accounts."zhihu-test"]\n'
        'platform = "zhihu"\n'
        f'runner_config = {json.dumps(str(runner))}\n'
        'profile = "zhihu-test"\n'
        'label = "Zhihu test account"\n',
        encoding="utf-8",
    )
    return registry


def _json(result):
    assert result.exit_code == 0, result.output
    return json.loads(result.output)


def test_task_cli_exposes_login_and_draft_platform_surfaces():
    assert set(main.commands) == {"platforms", "profiles", "zhihu", "xhs", "csdn"}
    assert main.commands["platforms"].hidden is False
    assert main.commands["profiles"].hidden is False

    zhihu = main.commands["zhihu"]
    assert set(zhihu.commands) == {"profiles", "login", "logout", "status", "draft"}
    assert zhihu.commands["profiles"].hidden is False
    assert zhihu.commands["login"].hidden is False
    assert zhihu.commands["logout"].hidden is False
    assert zhihu.commands["status"].hidden is False
    assert zhihu.commands["draft"].hidden is False

    xhs = main.commands["xhs"]
    assert set(xhs.commands) == {"profiles", "login", "logout", "status"}
    assert all(command.hidden is False for command in xhs.commands.values())

    csdn = main.commands["csdn"]
    assert set(csdn.commands) == {"profiles", "login", "logout", "status", "draft"}
    assert all(command.hidden is False for command in csdn.commands.values())


def test_top_level_tree_prints_complete_login_only_registered_cli_tree():
    result = CliRunner().invoke(main, ["--tree"])

    assert result.exit_code == 0, result.output
    assert "chatpost  # Browser-level platform login and draft manager." in result.output
    assert "├── --tree  # Print the registered CLI tree with command purpose and IO shape." in result.output
    assert "├── platforms [--output text|json] [-I/--no-interactive]  # List supported platforms without starting a browser." in result.output
    assert "├── profiles [--platform zhihu|xhs|csdn] [--registry REGISTRY] [--output text|json] [-I/--no-interactive]  # List configured browser Profiles without checking login state." in result.output
    assert "├── zhihu  # Zhihu browser login and Wechatsync draft capabilities." in result.output
    assert "│   ├── profiles [--registry REGISTRY] [--output text|json] [-I/--no-interactive]  # List configured Zhihu browser Profiles." in result.output
    assert "│   ├── login PROFILE [--registry REGISTRY] [--timeout TIMEOUT] [--output text|json] [-I/--no-interactive]  # Open/check a pure browser login session and emit a page-owned handoff." in result.output
    assert "│   └── draft PROFILE SOURCE [--registry REGISTRY] [--dry-run] [--receipt RECEIPT] [--output text|json] [-I/--no-interactive]  # Dry-run or create one Zhihu draft through Wechatsync; never final-publish." in result.output
    assert "├── xhs  # XHS browser login system." in result.output
    assert "│   ├── login PROFILE [--registry REGISTRY] [--timeout TIMEOUT] [--qrcode QRCODE-PATH] [--output text|json] [-I/--no-interactive]  # Open/check a pure browser login session and emit a page-owned handoff." in result.output
    assert "└── csdn  # CSDN browser login and Wechatsync draft capabilities." in result.output
    assert "    └── draft PROFILE SOURCE [--registry REGISTRY] [--dry-run] [--receipt RECEIPT] [--output text|json] [-I/--no-interactive]  # Dry-run or create one CSDN draft through Wechatsync; never final-publish." in result.output
    forbidden = [
        "account",
        "qr-artifact",
        "qr encode",
        "\n  qr",
        "WECHATSYNC_TOKEN",
        "MEDIA:ssh",
        "[media attachment]",
    ]
    for text in forbidden:
        assert text not in result.output


def test_cli_tree_is_generated_from_click_registry():
    source = (Path(__file__).resolve().parents[1] / "src/chatpost/cli.py").read_text(encoding="utf-8")

    stale_lines_name = "_CLI" + "_TREE" + "_LINES"
    stale_paths_name = "_CLI" + "_TREE" + "_COMMAND" + "_PATHS"

    assert stale_lines_name not in source
    assert stale_paths_name not in source
    assert 'render_command_tree(ctx.command, "chatpost")' in source


def test_top_level_help_shows_discovery_and_platform_groups_only():
    result = CliRunner().invoke(main, ["--help"])

    assert result.exit_code == 0, result.output
    assert "platforms" in result.output
    assert "profiles" in result.output
    assert "zhihu" in result.output
    assert "xhs" in result.output
    assert "csdn" in result.output
    assert "\n  account" not in result.output
    assert "\n  qr" not in result.output
    assert "\n  login" not in result.output
    assert "\n  post" not in result.output
    assert "--tree" in result.output


def test_platforms_lists_supported_login_platforms():
    result = CliRunner().invoke(main, ["platforms", "--output", "json", "-I"])
    payload = _json(result)

    assert payload == {
        "status": "READY",
        "platforms": [
            {
                "name": "zhihu",
                "profiles_command": "chatpost zhihu profiles",
                "login_command": "chatpost zhihu login PROFILE",
                "status_command": "chatpost zhihu status PROFILE",
                "logout_command": "chatpost zhihu logout PROFILE",
                "draft_command": "chatpost zhihu draft PROFILE SOURCE",
            },
            {
                "name": "xhs",
                "profiles_command": "chatpost xhs profiles",
                "login_command": "chatpost xhs login PROFILE",
                "status_command": "chatpost xhs status PROFILE",
                "logout_command": "chatpost xhs logout PROFILE",
            },
            {
                "name": "csdn",
                "profiles_command": "chatpost csdn profiles",
                "login_command": "chatpost csdn login PROFILE",
                "status_command": "chatpost csdn status PROFILE",
                "logout_command": "chatpost csdn logout PROFILE",
                "draft_command": "chatpost csdn draft PROFILE SOURCE",
            }
        ],
    }


def test_profiles_lists_browser_profile_configs_and_filters_platform(tmp_path):
    registry = _registry(tmp_path)

    result = CliRunner().invoke(
        main,
        ["profiles", "--platform", "zhihu", "--registry", str(registry), "--output", "json", "-I"],
    )
    payload = _json(result)

    assert payload["status"] == "READY"
    assert payload["profiles"] == [
        {
            "alias": "zhihu-test",
            "platform": "zhihu",
            "profile": "zhihu-test",
            "label": "Zhihu test account",
            "runner_config": str(tmp_path / "zhihu-runner.toml"),
        }
    ]
    lower = result.output.lower()
    assert "token" not in lower
    assert "cookie" not in lower
    assert "localstorage" not in lower


def test_zhihu_profiles_lists_zhihu_browser_profile_configs(tmp_path):
    registry = _zhihu_registry(tmp_path)

    result = CliRunner().invoke(
        main,
        ["zhihu", "profiles", "--registry", str(registry), "--output", "json", "-I"],
    )
    payload = _json(result)

    assert payload["status"] == "READY"
    assert payload["platform"] == "zhihu"
    assert payload["profiles"][0]["alias"] == "zhihu-test"


def test_top_level_profiles_filters_xiaohongshu_platform(tmp_path):
    registry = _registry(tmp_path)

    result = CliRunner().invoke(
        main,
        ["profiles", "--platform", "xhs", "--registry", str(registry), "--output", "json", "-I"],
    )
    payload = _json(result)

    assert payload["status"] == "READY"
    assert payload["platform"] == "xhs"
    assert payload["profiles"] == [
        {
            "alias": "xhs-test",
            "platform": "xhs",
            "profile": "xhs-test",
            "label": "XHS test account",
            "runner_config": str(tmp_path / "xhs-runner.toml"),
        }
    ]


def test_xiaohongshu_profiles_lists_xiaohongshu_browser_profile_configs(tmp_path):
    registry = _registry(tmp_path)

    result = CliRunner().invoke(
        main,
        ["xhs", "profiles", "--registry", str(registry), "--output", "json", "-I"],
    )
    payload = _json(result)

    assert payload["status"] == "READY"
    assert payload["platform"] == "xhs"
    assert payload["profiles"][0]["alias"] == "xhs-test"


def test_top_level_profiles_filters_csdn_platform(tmp_path):
    registry = _registry(tmp_path)

    result = CliRunner().invoke(
        main,
        ["profiles", "--platform", "csdn", "--registry", str(registry), "--output", "json", "-I"],
    )
    payload = _json(result)

    assert payload["status"] == "READY"
    assert payload["platform"] == "csdn"
    assert payload["profiles"] == [
        {
            "alias": "csdn-test",
            "platform": "csdn",
            "profile": "csdn-test",
            "label": "CSDN test account",
            "runner_config": str(tmp_path / "csdn-runner.toml"),
        }
    ]


def test_csdn_profiles_lists_csdn_browser_profile_configs(tmp_path):
    registry = _registry(tmp_path)

    result = CliRunner().invoke(
        main,
        ["csdn", "profiles", "--registry", str(registry), "--output", "json", "-I"],
    )
    payload = _json(result)

    assert payload["status"] == "READY"
    assert payload["platform"] == "csdn"
    assert payload["profiles"][0]["alias"] == "csdn-test"
