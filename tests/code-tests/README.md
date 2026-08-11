# Code Tests

Non-CLI code tests live here.

Current focused gates:

```bash
export PYTHONPATH=src
python -m pytest -q tests/test_zhihu_flow.py tests/test_xhs_flow.py tests/test_csdn_flow.py
```

The flow tests keep the implementation honest:

- `load_browser_config()` stays browser-only for `login/status/logout` and does not require extension/env/bridge fields.
- `load_runner_config()` is the only draft path that reads Wechatsync extension, CLI, env, and bridge fields.
- CSDN dry-run shells out to Wechatsync with `--platforms csdn`.
- CSDN create sends `syncArticle` through the extension MCP bridge with platform `csdn` and accepts only `draftOnly=true` results.
- Receipts are mode `0600`; create never implies public publish.
