import argparse
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

try:
    from .downloader import AssetDownloader
    from .models import ResolvedSegment
    from .parser import parse_job_file
    from .renderer import render_job
    from .timeline import build_sequence_nodes
except ImportError:
    # Allow running as a script in IDE: `python app/main.py`
    import sys

    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))

    from app.downloader import AssetDownloader
    from app.models import ResolvedSegment
    from app.parser import parse_job_file
    from app.renderer import render_job
    from app.timeline import build_sequence_nodes


def run(job_path: Path, output_dir: Path, cache_dir: Path) -> Path:
    job = parse_job_file(job_path)
    sequence = build_sequence_nodes(job)
    if not sequence:
        raise ValueError("No nodes found in job config.")

    downloader = AssetDownloader(cache_root=cache_dir)
    segments: list[ResolvedSegment] = []

    for group_id, kind, node in sequence:
        image_path = downloader.fetch(node.image_url, "images")
        voice_path = downloader.fetch(node.voice_url, "audio") if node.voice_url else None
        segments.append(
            ResolvedSegment(
                group_id=group_id,
                kind=kind,
                image_path=image_path,
                comment=node.comment,
                voice_path=voice_path,
            )
        )

    bgm_path = downloader.fetch(job.audio.bgm_url, "audio") if job.audio.bgm_url else None

    output_path = output_dir / job.output.filename
    return render_job(job=job, segments=segments, bgm_path=bgm_path, output_path=output_path)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="JSON-driven video composer")
    parser.add_argument("--job", help="Path to a single job json file")
    parser.add_argument(
        "--jobs-dir",
        default="jobs",
        help="Directory containing job json files (default: jobs)",
    )
    parser.add_argument(
        "--output-dir",
        default="outputs",
        help="Output directory (default: outputs)",
    )
    parser.add_argument(
        "--cache-dir",
        default="cache",
        help="Asset cache directory (default: cache)",
    )
    return parser


def _resolve_path(raw_path: str, base: Path) -> Path:
    path = Path(raw_path)
    if path.is_absolute():
        return path.resolve()
    return (base / path).resolve()


def main() -> None:
    parser = build_arg_parser()
    args = parser.parse_args()
    output_dir = _resolve_path(args.output_dir, PROJECT_ROOT)
    cache_dir = _resolve_path(args.cache_dir, PROJECT_ROOT)

    if args.job:
        job_paths = [_resolve_path(args.job, PROJECT_ROOT)]
    else:
        jobs_dir = _resolve_path(args.jobs_dir, PROJECT_ROOT)
        job_paths = sorted(jobs_dir.glob("*.json"))
        if not job_paths:
            raise FileNotFoundError(f"No json jobs found in: {jobs_dir}")

    succeeded: list[Path] = []
    failed: list[tuple[Path, str]] = []

    for job_path in job_paths:
        print(f"[START] {job_path}")
        try:
            output = run(job_path=job_path, output_dir=output_dir, cache_dir=cache_dir)
            print(f"[OK] {job_path.name} -> {output}")
            succeeded.append(job_path)
        except Exception as err:
            print(f"[FAIL] {job_path.name}: {err}")
            failed.append((job_path, str(err)))

    print("\n=== Summary ===")
    print(f"Total: {len(job_paths)} | Success: {len(succeeded)} | Failed: {len(failed)}")
    if failed:
        for job_path, reason in failed:
            print(f"- {job_path.name}: {reason}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
