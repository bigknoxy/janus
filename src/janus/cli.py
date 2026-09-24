"""Janus CLI — the two faces at the gate.

  janus "fix calculate_tax in calc.py" --root .
  janus doctor --root .
"""

import sys
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from janus.context.repo_map import repo_map
from janus.core.config import JanusSettings
from janus.core.orchestrator import PipelineOrchestrator, RunReport, RunStatus
from janus.core.types import IntentType, System1Decision
from janus.system1.base import DecisionEngineProtocol
from janus.system1.mock_engine import MockDecisionEngine
from janus.system2.client import LocalGenerativeEngine

app = typer.Typer(add_completion=False, no_args_is_help=False)
console = Console()


def _build_s1(settings: JanusSettings) -> DecisionEngineProtocol:
    if settings.s1_backend == "laya":
        from janus.system1.laya_engine import LayaDecisionEngine

        return LayaDecisionEngine(settings)
    if settings.s1_backend == "mock":
        return MockDecisionEngine(settings)
    raise typer.BadParameter(f"unknown s1 backend: {settings.s1_backend!r}")


def _render_decision(decision: System1Decision) -> None:
    table = Table.grid(padding=(0, 2))
    table.add_row("intent", f"[bold]{decision.intent}[/bold]")
    table.add_row("confidence", f"{decision.confidence:.2f}")
    if decision.target_files:
        table.add_row("files", ", ".join(decision.target_files))
    if decision.target_symbols:
        table.add_row("symbols", ", ".join(decision.target_symbols))
    console.print(Panel(table, title="🚪 System 1", border_style="blue"))


def _render_report(report: RunReport) -> int:
    _render_decision(report.decision)
    status_style = {
        RunStatus.PATCHED_VERIFIED: "green",
        RunStatus.FAILED_ROLLED_BACK: "red",
        RunStatus.ESCALATE: "yellow",
        RunStatus.READ_ONLY: "cyan",
        RunStatus.DIRECT_ACTION: "cyan",
    }[report.status]
    body = report.message or f"{len(report.patches)} patch block(s)"
    if report.verification is not None:
        body += f"\nverify: exit {report.verification.exit_code}"
    console.print(Panel(body, title=f"⚡ {report.status}", border_style=status_style))
    return 0 if report.status == RunStatus.PATCHED_VERIFIED else 1


@app.command()
def run(
    prompt: Annotated[str | None, typer.Argument(help="The request for Janus")] = None,
    root: Annotated[str, typer.Option(help="Repo root to operate on")] = ".",
    s1_backend: Annotated[str, typer.Option(help="laya | mock")] = "mock",
    model: Annotated[str | None, typer.Option(help="Override the S2 model")] = None,
    s2_url: Annotated[str | None, typer.Option(help="Override the S2 base URL")] = None,
    threshold: Annotated[
        float | None, typer.Option(help="Confidence threshold (default 0.85)")
    ] = None,
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Skip escalation prompts")] = False,
) -> None:
    """Route a request through the dual-core pipeline."""
    if prompt is None:
        prompt = typer.prompt("What should Janus do")

    overrides: dict[str, object] = {"s1_backend": s1_backend}
    if model:
        overrides["s2_model"] = model
    if s2_url:
        overrides["s2_base_url"] = s2_url
    if threshold is not None:
        overrides["confidence_threshold"] = threshold
    settings = JanusSettings(**overrides)  # type: ignore[arg-type]

    root_path = str(Path(root).resolve())
    summary = repo_map(root_path)

    orchestrator = PipelineOrchestrator(
        s1=_build_s1(settings),
        s2=LocalGenerativeEngine(settings),
        settings=settings,
    )
    report = orchestrator.run(prompt, root_path, summary)

    if (
        report.status == RunStatus.ESCALATE
        and not yes
        and sys.stdin.isatty()
        and typer.confirm(f"{report.message}\nProceed anyway with a best-effort attempt?")
    ):
        # Best-effort: strip the modulation gate by forcing the intent and
        # re-running; S2 still gets nothing unless S1 meant modification.
        forced = report.decision.model_copy(
            update={"intent": IntentType.CODE_MODIFICATION, "requires_s2": True}
        )
        report = orchestrator.run_forced(forced, root_path)

    raise typer.Exit(code=_render_report(report))


@app.command()
def doctor(
    root: Annotated[str, typer.Option()] = ".",
    s1_backend: Annotated[str, typer.Option(help="laya | mock")] = "laya",
    s2_url: Annotated[str | None, typer.Option()] = None,
) -> None:
    """Check the moving parts: Laya install, S2 endpoint, repo map."""
    settings = JanusSettings(s1_backend=s1_backend)
    if s2_url:
        settings = settings.model_copy(update={"s2_base_url": s2_url})

    table = Table(title="🩺 janus doctor")
    table.add_column("check")
    table.add_column("status")
    table.add_column("detail")

    # System 1
    if settings.s1_backend == "laya":
        try:
            import laya  # noqa: F401

            table.add_row("system1 (laya)", "✅", f"installed ({laya.__name__})")
        except ImportError:
            table.add_row("system1 (laya)", "❌", "pip install janus-code[laya]")
    else:
        table.add_row("system1 (mock)", "✅", "offline deterministic engine")

    # System 2 endpoint
    import httpx

    url = f"{settings.s2_base_url.rstrip('/')}/models"
    try:
        resp = httpx.get(url, timeout=5.0)
        names = [m.get("id", "?") for m in resp.json().get("data", [])][:5]
        table.add_row("system2 endpoint", "✅", f"{url} → {', '.join(names) or 'no models listed'}")
    except Exception as e:
        table.add_row("system2 endpoint", "❌", str(e)[:80])

    # Repo map
    summary = repo_map(str(Path(root).resolve()))
    n = len(summary.splitlines())
    table.add_row("repo map", "✅" if n else "⚠️", f"{n} file line(s), {len(summary)} chars")

    console.print(table)


if __name__ == "__main__":
    app()
