from pathlib import Path

import typer

from ultratokenkiller.reference_runner import generate_reference


def main(
    headroom: Path = typer.Option(..., exists=True, file_okay=False),
    rtk: Path = typer.Option(..., exists=True, file_okay=False),
    caveman: Path = typer.Option(..., exists=True, file_okay=False),
    output: Path = typer.Option(..., dir_okay=False),
    python: Path | None = typer.Option(None, exists=True, dir_okay=False),
) -> None:
    """Generate a validated, fixed-commit input reference package."""
    result = generate_reference(
        headroom=headroom,
        rtk=rtk,
        caveman=caveman,
        output=output,
        python=python,
    )
    typer.echo(f"wrote {output} ({len(result['outputs'])} input cases, 0 model calls)")


if __name__ == "__main__":
    typer.run(main)
