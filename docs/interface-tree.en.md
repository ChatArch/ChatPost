# Python Interface Tree

The ChatPost CLI should remain a thin entry point. Substantive behavior belongs in importable Python functions, classes, or service layers.

## Package Entry

```python
from chatpost import __version__
```

## Planned Interfaces

```text
chatpost
├── cli.py          # Click entry point; argument parsing and output only
└── <service>.py    # Importable package behavior
```

## Update Checklist

- Every substantive CLI command maps to an importable API.
- Function signatures in documentation match the implementation.
- Public output does not expose tokens, cookies, internal URLs, or personal information by default.
