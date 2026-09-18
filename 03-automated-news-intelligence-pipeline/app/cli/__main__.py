"""python -m app.cli entrypoint."""

from app.cli.app import cli, main

if __name__ == "__main__":
    main()

__all__ = ["cli", "main"]
