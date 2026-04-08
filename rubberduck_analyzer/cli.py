"""CLI entry point for RubberDuck Interview Analyzer."""

from __future__ import annotations

from pathlib import Path

import click


@click.group()
@click.version_option(version="0.1.0")
def main():
    """RubberDuck Interview Analyzer — analyze user testing sessions."""


@main.command()
@click.option("--transcript", required=True, type=click.Path(exists=True), help="Path to transcript file")
@click.option("--video", type=click.Path(exists=True), help="Path to video recording")
@click.option("--output", type=click.Path(), help="Output JSON path (default: data/sessions/)")
@click.option("--tester-name", help="Override tester name")
@click.option("--facilitator-is-first/--tester-is-first", default=True, help="Speaker order for timestamped transcripts")
def analyze_m1(transcript, video, output, tester_name, facilitator_is_first):
    """Analyze an M1 live interview session."""
    from rubberduck_analyzer.analyzers.m1_analyzer import analyze_m1 as run_m1

    result = run_m1(
        transcript_path=transcript,
        video_path=video,
        output_path=output,
        tester_name=tester_name,
        facilitator_is_first=facilitator_is_first,
    )
    click.echo(f"Analysis complete. Observations extracted for {result['tester'].get('name', 'unknown')}.")


@main.command()
@click.option("--video", type=click.Path(exists=True), help="Path to screen recording")
@click.option("--written", required=True, type=click.Path(exists=True), help="Path to written deliverable (3-5 sentences)")
@click.option("--transcript", type=click.Path(exists=True), help="Optional transcript")
@click.option("--output", type=click.Path(), help="Output JSON path")
@click.option("--tester-name", help="Tester name")
def analyze_m2(video, written, transcript, output, tester_name):
    """Analyze an M2 independent-use deliverable."""
    from rubberduck_analyzer.analyzers.m2_analyzer import analyze_m2 as run_m2

    result = run_m2(
        video_path=video,
        written_path=written,
        transcript_path=transcript,
        output_path=output,
        tester_name=tester_name,
    )
    rec = result.get("m3_recommendation", "unknown")
    click.echo(f"M2 analysis complete. M3 recommendation: {rec}.")


@main.command()
@click.option("--video-without", required=True, type=click.Path(exists=True), help="Video of task WITHOUT RubberDuck")
@click.option("--video-with", required=True, type=click.Path(exists=True), help="Video of task WITH RubberDuck")
@click.option("--comparison", required=True, type=click.Path(exists=True), help="Written comparison")
@click.option("--proposal", required=True, type=click.Path(exists=True), help="Task proposal")
@click.option("--output", type=click.Path(), help="Output JSON path")
@click.option("--tester-name", help="Tester name")
def analyze_m3(video_without, video_with, comparison, proposal, output, tester_name):
    """Analyze an M3 proof-of-value comparison."""
    from rubberduck_analyzer.analyzers.m3_analyzer import analyze_m3 as run_m3

    result = run_m3(
        video_without_path=video_without,
        video_with_path=video_with,
        comparison_path=comparison,
        proposal_path=proposal,
        output_path=output,
        tester_name=tester_name,
    )
    etype = result.get("evidence_type", "unknown")
    click.echo(f"M3 analysis complete. Evidence type: {etype}.")


@main.command()
@click.option("--sessions-dir", required=True, type=click.Path(exists=True), help="Directory containing session JSONs")
@click.option("--output", type=click.Path(), help="Output directory for reports")
def synthesize(sessions_dir, output):
    """Cross-tester synthesis — requires 3+ sessions."""
    from rubberduck_analyzer.synthesizer.cross_tester import synthesize_sessions

    result = synthesize_sessions(
        sessions_dir=sessions_dir,
        output_dir=output,
    )
    n = result.get("session_count", 0)
    click.echo(f"Synthesis complete across {n} sessions.")


@main.command("ingest-context")
@click.option("--file", "file_path", required=True, type=click.Path(exists=True), help="Path to context document")
@click.option("--type", "doc_type", required=True, type=click.Choice(["whitepaper", "competitive", "kpi", "roadmap", "changelog"]))
def ingest_context(file_path, doc_type):
    """Ingest a product context document for use during analysis."""
    from rubberduck_analyzer.context.product_context import ingest_document

    result = ingest_document(file_path=file_path, doc_type=doc_type)
    chunks = result.get("chunk_count", 0)
    click.echo(f"Ingested {chunks} chunks from {doc_type} document.")


if __name__ == "__main__":
    main()
