# CLI Tests

Real CLI tests live here.

Current release gate examples:

```bash
export PYTHONPATH=src
python -m pytest -q tests/test_task_cli.py tests/test_zhihu_cli.py tests/test_xhs_cli.py tests/test_csdn_cli.py
python -m chatpost.cli --tree
python -m chatpost.cli csdn draft --help
```

The CLI tests lock the public command tree and the browser-vs-adapter boundary:

- `platforms` and `profiles` include `zhihu`, `xhs`, and `csdn`.
- `zhihu` and `csdn` expose `profiles/login/status/logout/draft`.
- `xhs` exposes only `profiles/login/status/logout`.
- `csdn draft` is a Wechatsync draft entrypoint; it is not a hand-written CSDN editor/CDP automation path and it is not public `post/publish`.
