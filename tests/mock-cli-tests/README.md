# Mock CLI Tests

Mock/fake CLI tests live here.

Use this directory for tests that exercise rendering, command registration, or parser behavior without starting a real browser, Wechatsync bridge, or networked platform session. Browser login status, QR handoff, and CSDN/Zhihu Wechatsync draft contracts belong in the normal `tests/test_*_flow.py` suites with explicit fakes/monkeypatches.
