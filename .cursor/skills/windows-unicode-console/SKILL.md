---
name: windows-unicode-console
description: >-
  Prevents Windows UnicodeEncodeError (charmap codec) when running Python
  or scripts that print Unicode such as arrows (→), umlauts or ß. Use on
  Windows before any native shell Python invocation (including pytest), when
  UnicodeEncodeError or charmap_encode appears, or when output contains →.
---

# Windows Unicode console (charmap fix)

## Problem

On Windows PowerShell, Python stdout often uses the **cp1252/charmap** codec. Printing or logging strings with characters outside that set (`→`, umlauts in German tariff names) can raise:

```text
UnicodeEncodeError: 'charmap' codec can't encode character '→' ...
```

**Do not** strip Unicode from docs, tariff labels, or examples to fix this. Fix the **console encoding** instead.

## Agent rule: every Python shell command on Windows

Before **any** Python invocation in the Shell tool, set UTF-8 for that command:

```powershell
$env:PYTHONIOENCODING='utf-8'; $env:PYTHONUTF8='1'; python -m pytest -q
```

| Variable | Purpose |
|----------|---------|
| `PYTHONIOENCODING=utf-8` | Forces stdin/stdout/stderr to UTF-8 |
| `PYTHONUTF8=1` | Enables Python UTF-8 mode |

Use the shell tool's working directory for the project root; do **not** use `&&` in PowerShell 5.x.

## If UnicodeEncodeError already occurred

1. Re-run the **same command** with the env prefix above.
2. Do **not** edit source files to replace `→` with `->` unless the user explicitly asks for ASCII-only output.
3. If the error is in **new** CLI code, add the reconfigure block below at entry.

## New CLI entry points

```python
import sys


def _configure_console_utf8() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def main() -> int:
    _configure_console_utf8()
    ...
```

## Files

Always read and write text files with `encoding="utf-8"` (JSON examples, catalog packages, user tariffs). Charmap errors are almost always **console** encoding; do not "fix" them by changing file encodings.

## Checklist

- [ ] Windows shell command includes `$env:PYTHONIOENCODING='utf-8'; $env:PYTHONUTF8='1';`
- [ ] New CLI calls `_configure_console_utf8()` in `main()`
- [ ] On failure, re-run with env vars; do not patch Unicode out of strings
