"""Explicit admin command: python -m app.db.setup_checkpointer."""

import asyncio
import os
import sys
from contextlib import redirect_stderr, redirect_stdout


def main() -> int:
    try:
        with open(os.devnull, "w", encoding="utf-8") as sink:
            with redirect_stdout(sink), redirect_stderr(sink):
                # Import configuration inside the safe CLI boundary so malformed
                # settings cannot print tracebacks or configuration values.
                from app.db.checkpointer import setup_checkpointer

                asyncio.run(
                    setup_checkpointer(),
                    loop_factory=asyncio.SelectorEventLoop if sys.platform == "win32" else None,
                )
    except Exception:
        print("Checkpoint initialization failed. Check configuration and database availability.")
        return 1
    print("Checkpoint initialization succeeded.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
