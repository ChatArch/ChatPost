# CLI Capability Map

This page is the compact capability map for the `ChatPost` CLI. Use it to review which commands are first-class entries and which are still boundary or planned slots. After scaffolding, update it with the real command tree; do not present unimplemented commands as available operations.

Importable Python functions are mapped in [Interface Tree](interface-tree.md). Current package boundaries are tracked in [Capability Map](capability-map.md).

## Top-Level Commands

```text
chatpost                  # ChatPost command-line entry
├── --help                     # Show CLI help and registered commands
└── --version                  # Print the current package version
```

## Base Entries

```text
chatpost --help           # Verify the command is installed and inspect the current command tree
chatpost --version        # Verify the installed version
```

`--help` and `--version` are the scaffolded verification entries. After adding business commands, follow the ChatTea CLI tree pattern: split command groups into their own sections and annotate every command line.

## Business Command Slots

```text
chatpost <group>          # Command group named after real package capability
├── <command>                  # Explain what this command does
└── <command>                  # Explain status, boundary, or checkpoint behavior
```

This is a structural placeholder, not a promise of future capability. Only document a command as implemented after the command, Python function, and tests exist.

## Status Contract

| Status | Meaning |
| --- | --- |
| Implemented | Command, function, and tests exist |
| Verified | Covered by CI, local smoke, or real-service practice |
| Planned / checkpoint | Keep only boundary notes; do not write operation tutorials before implementation |

## Implementation Contract

- Every implemented command must map back to a Python function, class, or service layer.
- If a command writes remote state, document credentials, permissions, dry-run/checkpoint behavior, or confirmation boundaries.
- When adding a command, update README, the interface tree, capability map, tests, and related flow pages together.
