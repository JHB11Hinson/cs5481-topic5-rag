"""Minimal test runner: `python -m ragqa.selftest`.

The project needs a test command that works with nothing installed beyond the
standard library, so this walks the `tests` package for `test_*` functions. Once
pytest is available the same files run under it unchanged.
"""

from __future__ import annotations

import importlib
import pkgutil
import sys
import traceback


def main() -> int:
    try:
        import tests
    except ImportError:
        print("no tests package found", file=sys.stderr)
        return 1

    passed = 0
    failed = []

    for module_info in pkgutil.iter_modules(tests.__path__, "tests."):
        module = importlib.import_module(module_info.name)
        for name in sorted(dir(module)):
            if not name.startswith("test_"):
                continue
            function = getattr(module, name)
            if not callable(function):
                continue
            label = f"{module_info.name}.{name}"
            try:
                function()
            except Exception:
                failed.append(label)
                print(f"FAIL {label}")
                traceback.print_exc()
            else:
                passed += 1
                print(f"ok   {label}")

    print(f"\n{passed} passed, {len(failed)} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
