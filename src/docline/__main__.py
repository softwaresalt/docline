"""Package entrypoint for ``python -m docline``."""

from docline.cli import main as cli_main


def main() -> int:
    """Run the package entrypoint.

    Returns:
        Process exit code.
    """
    return cli_main()


if __name__ == "__main__":
    raise SystemExit(main())
