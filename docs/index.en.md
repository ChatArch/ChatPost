# ChatPost Docs

ChatPost is ChatArch's multi-platform content publishing control plane. This site keeps the verified Zhihu browser path, first functional design, and currently implemented behavior visibly separate.

Site entry: <https://arch.gh.wzhecnu.cn/ChatPost/en/>

## Choose Documentation by Scenario

| Scenario | Document |
| --- | --- |
| Understand the control plane, Browser Runner, Account, and Publication model | [Overall Architecture](architecture.md) |
| Review Chrome installation, ChatEnv, URLs, profiles, and ledger | [Configuration, Environment, and State](configuration.md) |
| Follow first Zhihu login/draft acceptance with the fixed MkDocs article | [Zhihu First Setup and Draft Acceptance](zhihu-first-run.md) |
| Install the package, run the CLI, and confirm it works | [CLI Tree](cli-tree.md) |
| Review the proposed CLI, Chrome runtime, and multi-account isolation | [Browser Runners and Account Isolation](browser-runners.md) |
| Check first-class capabilities and current boundaries | [Capability Map](capability-map.md) |
| Call package behavior directly from Python | [Python Interface Tree](interface-tree.md) |

## Documentation Organization

This site keeps durable documentation entry points instead of a generic roadmap:

- **Overall architecture**: control-plane, execution-plane, and core-resource ownership.
- **Configuration, environment, and state**: Chrome installation, ChatEnv secrets, runner state, and publication ledger.
- **Zhihu first setup and acceptance**: a fixed article defines visible login and one draft-create acceptance.
- **CLI tree**: the most direct command entry point, including the real command tree, status, and update checklist.
- **Browser runners and account isolation**: host binaries, Docker, user-data-dir isolation, and bridge boundaries.
- **Capability map**: first-class capabilities, boundaries, and out-of-scope areas.
- **Interface tree**: importable Python APIs behind the CLI.

## Primary Entry Points

<div class="grid cards" markdown>

- **Overall Architecture**

    Start with how the ChatUp dependency plus Runner, Account, and Publication form the control and execution planes.

    [Open Architecture](architecture.md)

- **Configuration, Environment, and State**

    Review ChatArch-managed Chrome, the three connection surfaces, ChatEnv secrets, and filesystem ownership.

    [Open Configuration Design](configuration.md)

- **Zhihu First Setup and Draft Acceptance**

    Follow visible login, planning, one draft create, and readback using the fixed MkDocs article.

    [Open Zhihu Task Flow](zhihu-first-run.md)

- **CLI Tree**

    Start from the CLI entry point and record implemented commands, command status, and interactive conventions.

    [Open CLI Tree](cli-tree.md)

- **Capability Map**

    Review current package boundaries and avoid presenting planned work as implemented behavior.

    [Open Capability Map](capability-map.md)

- **Browser Runners and Account Isolation**

    Review whether Chrome requires Docker, how multiple accounts are isolated, and how runners relate to accounts.

    [Open Browser Runner Design](browser-runners.md)

- **Python Interface Tree**

    Keep the CLI thin and put substantive behavior in importable Python APIs.

    [Open Interface Tree](interface-tree.md)

</div>

## Documentation Status

- **Implemented**: code, tests, or CLI routes exist.
- **Verified**: covered by local smoke, CI, or real-service practice.
- **Not implemented**: keep as boundary and planning notes only; turn into operation docs after implementation and validation.

## Local Preview

```bash
python -m pip install -e ".[docs]"
mkdocs serve
```

The Chinese home page is available at <https://arch.gh.wzhecnu.cn/ChatPost/>. Topic pages without English translations fall back to the default Chinese content through the i18n plugin.
