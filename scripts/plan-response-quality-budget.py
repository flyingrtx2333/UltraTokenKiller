import json
from pathlib import Path

import typer

from ultratokenkiller.response_benchmark import plan_response_budget


def main(
    corpus: Path = typer.Option(
        Path("src/ultratokenkiller/data/response-quality-corpus.json"),
        exists=True,
        dir_okay=False,
    ),
    output: Path | None = typer.Option(None),
) -> None:
    report = plan_response_budget(corpus)
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8")
    typer.echo(rendered, nl=False)


if __name__ == "__main__":
    typer.run(main)
