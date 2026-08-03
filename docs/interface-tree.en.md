# Python Interface Tree

The ChatPost CLI should remain a thin entry point. Substantive behavior belongs in importable Python functions, classes, or service layers.

## Package Entry

```python
from chatpost import __version__
```

## Planned Interfaces

```text
chatpost
├── cli.py           # Click entry point; argument parsing and output only
├── dependencies.py  # Resolve a ChatUp Chrome descriptor read-only; never install
├── runner.py        # Profile/process/CDP/bridge lifecycle
├── account.py       # platform@alias and login checkpoint
└── publication.py   # Plan/draft/ledger/reconcile
```

The Chrome environment contract consumes ChatUp's released public API directly:

```python
from chatup.chrome import ChromeInstallation, resolve_chrome
```

The ChatPost dependency adapter may only wrap `resolve_chrome(...)` and domain errors. It never copies the downloader/extractor and never calls `ensure_chrome(...)` implicitly from `runner start`.

## Update Checklist

- Every substantive CLI command maps to an importable API.
- Function signatures in documentation match the implementation.
- Public output does not expose tokens, cookies, internal URLs, or personal information by default.
