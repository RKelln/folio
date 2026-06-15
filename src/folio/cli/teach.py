"""folio teach — interactive tutorial."""

from __future__ import annotations

from folio import __version__


def main(argv: list[str] | None = None):
    if argv and "--help" in argv:
        print("folio teach — interactive tutorial (coming soon)")
        print("Usage: folio teach")
        return
    if argv and "--version" in argv:
        print(f"folio teach v{__version__}")
        return
    print("folio teach — not yet implemented")


if __name__ == '__main__':
    main()
