from pathlib import Path

import typer

from ultratokenkiller.caveman_reference import generate_caveman_reference


def main(
    checkout: Path = typer.Option(..., exists=True, file_okay=False),
    output: Path = typer.Option(..., dir_okay=False),
) -> None:
    result = generate_caveman_reference(checkout, output)
    typer.echo(
        f"wrote {output} ({len(result['active_modes'])} active modes, "
        f"{len(result['rules'])} rules, 0 model calls)"
    )


if __name__ == "__main__":
    typer.run(main)
