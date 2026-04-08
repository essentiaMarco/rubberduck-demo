"""Background task wrappers that run analyzers and update job status."""

from __future__ import annotations

import traceback
from pathlib import Path

from rubberduck_analyzer.web.models import update_job


def run_m1_analysis(
    job_id: str,
    transcript_path: str,
    video_path: str | None,
    tester_name: str | None,
    facilitator_is_first: bool,
):
    """Background task: run M1 analysis and update job status."""
    try:
        update_job(job_id, "running")
        from rubberduck_analyzer.analyzers.m1_analyzer import analyze_m1

        output_path = Path("data/sessions") / f"{job_id}.json"
        analyze_m1(
            transcript_path=transcript_path,
            video_path=video_path,
            output_path=output_path,
            tester_name=tester_name,
            facilitator_is_first=facilitator_is_first,
        )
        update_job(job_id, "completed", result_path=str(output_path))
    except Exception as e:
        update_job(job_id, "failed", error=f"{e}\n{traceback.format_exc()}")


def run_m2_analysis(
    job_id: str,
    written_path: str,
    video_path: str | None,
    transcript_path: str | None,
    tester_name: str | None,
):
    """Background task: run M2 analysis and update job status."""
    try:
        update_job(job_id, "running")
        from rubberduck_analyzer.analyzers.m2_analyzer import analyze_m2

        output_path = Path("data/sessions") / f"{job_id}.json"
        analyze_m2(
            video_path=video_path,
            written_path=written_path,
            transcript_path=transcript_path,
            output_path=output_path,
            tester_name=tester_name,
        )
        update_job(job_id, "completed", result_path=str(output_path))
    except Exception as e:
        update_job(job_id, "failed", error=f"{e}\n{traceback.format_exc()}")


def run_m3_analysis(
    job_id: str,
    video_without_path: str,
    video_with_path: str,
    comparison_path: str,
    proposal_path: str,
    tester_name: str | None,
):
    """Background task: run M3 analysis and update job status."""
    try:
        update_job(job_id, "running")
        from rubberduck_analyzer.analyzers.m3_analyzer import analyze_m3

        output_path = Path("data/sessions") / f"{job_id}.json"
        analyze_m3(
            video_without_path=video_without_path,
            video_with_path=video_with_path,
            comparison_path=comparison_path,
            proposal_path=proposal_path,
            output_path=output_path,
            tester_name=tester_name,
        )
        update_job(job_id, "completed", result_path=str(output_path))
    except Exception as e:
        update_job(job_id, "failed", error=f"{e}\n{traceback.format_exc()}")


def run_synthesis(job_id: str, sessions_dir: str, output_dir: str | None):
    """Background task: run cross-tester synthesis."""
    try:
        update_job(job_id, "running")
        from rubberduck_analyzer.synthesizer.cross_tester import synthesize_sessions

        out = output_dir or "data/reports"
        synthesize_sessions(sessions_dir=sessions_dir, output_dir=out)
        update_job(job_id, "completed", result_path=out)
    except Exception as e:
        update_job(job_id, "failed", error=f"{e}\n{traceback.format_exc()}")
