import argparse
import shutil
import subprocess
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
        # New format: each node has narrations[].
        # Expand one node into multiple segments (same image, different narration).
        if node.narrations:
            for narration in node.narrations:
                voice_path = (
                    downloader.fetch(narration.voice_url, "audio")
                    if narration.voice_url
                    else None
                )
                segments.append(
                    ResolvedSegment(
                        group_id=group_id,
                        kind=kind,
                        image_path=image_path,
                        comment=narration.comment,
                        voice_path=voice_path,
                    )
                )
        else:
            # No narration: keep one still segment with default duration.
            segments.append(
                ResolvedSegment(
                    group_id=group_id,
                    kind=kind,
                    image_path=image_path,
                    comment="",
                    voice_path=None,
                )
            )

    bgm_path = downloader.fetch(job.audio.bgm_url, "audio") if job.audio.bgm_url else None
    cover_path = downloader.fetch(job.output.cover, "images") if job.output.cover else None

    output_path = output_dir / job.output.filename
    rendered_output = render_job(
        job=job,
        segments=segments,
        bgm_path=bgm_path,
        cover_path=cover_path,
        output_path=output_path,
    )
    if cover_path:
        _attach_cover_art(rendered_output, cover_path)
    return rendered_output


def _attach_cover_art(video_path: Path, cover_path: Path) -> None:
    ffmpeg_bin = shutil.which("ffmpeg")
    if not ffmpeg_bin:
        print("[WARN] ffmpeg not found in PATH. Skip attached cover metadata.")
        return
    if not video_path.exists() or not cover_path.exists():
        return

    tmp_path = video_path.with_name(f"{video_path.stem}.with_cover{video_path.suffix}")
    cmd = [
        ffmpeg_bin,
        "-y",
        "-i",
        str(video_path),
        "-i",
        str(cover_path),
        "-map",
        "0",
        "-map",
        "1",
        "-c",
        "copy",
        "-c:v:1",
        "mjpeg",
        "-disposition:v:1",
        "attached_pic",
        str(tmp_path),
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        tmp_path.replace(video_path)
    except subprocess.CalledProcessError as err:
        print(f"[WARN] Failed to attach cover metadata: {err.stderr.strip()}")
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass


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
