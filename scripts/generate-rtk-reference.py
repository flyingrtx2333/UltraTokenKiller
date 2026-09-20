import json
from pathlib import Path

import typer

from ultratokenkiller.rtk_reference import compare_rtk_reference, generate_rtk_reference


def main(
    checkout: Path = typer.Option(..., exists=True, file_okay=False),
    binary: Path = typer.Option(..., exists=True, dir_okay=False),
    output: Path = typer.Option(..., dir_okay=False),
    comparison: Path | None = typer.Option(None, dir_okay=False),
) -> None:
    result = generate_rtk_reference(checkout=checkout, binary=binary, output=output)
    if comparison:
        report = compare_rtk_reference(output)
        comparison.parent.mkdir(parents=True, exist_ok=True)
        comparison.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    typer.echo(f"wrote {output} ({len(result['cases'])} captured-output cases, 0 model calls)")


if __name__ == "__main__":
    typer.run(main)
