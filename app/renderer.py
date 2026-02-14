from pathlib import Path

from moviepy import (
    AudioFileClip,
    ColorClip,
    CompositeAudioClip,
    CompositeVideoClip,
    ImageClip,
    TextClip,
    vfx,
)

from .models import JobSpec, ResolvedSegment


def _fit_center(clip, width: int, height: int):
    scale = min(width / clip.w, height / clip.h)
    new_w = max(2, int(clip.w * scale))
    new_h = max(2, int(clip.h * scale))
    if new_w % 2 != 0:
        new_w -= 1
    if new_h % 2 != 0:
        new_h -= 1
    return clip.resized((new_w, new_h)).with_position("center")


def render_job(
    job: JobSpec,
    segments: list[ResolvedSegment],
    output_path: Path,
    bgm_path: Path | None = None,
) -> Path:
    if not segments:
        raise ValueError("No segments to render.")

    canvas = job.output.canvas
    transition = max(0.0, job.timeline.transition_sec)
    default_still = max(0.1, job.timeline.default_still_sec)
    voice_offset = max(0.0, job.timeline.voice_start_offset_sec)

    opened_audio_sources: list[AudioFileClip] = []
    video_layers = []
    subtitle_layers = []
    audio_tracks = []

    cursor = 0.0
    durations: list[float] = []
    starts: list[float] = []

    try:
        for idx, seg in enumerate(segments):
            voice_src = None
            voice_duration = 0.0
            if seg.voice_path and seg.voice_path.exists():
                voice_src = AudioFileClip(str(seg.voice_path))
                opened_audio_sources.append(voice_src)
                voice_duration = voice_src.duration

            segment_duration = max(default_still, voice_duration + voice_offset)
            start = cursor if idx == 0 else cursor - transition
            starts.append(start)
            durations.append(segment_duration)

            clip = ImageClip(str(seg.image_path), duration=segment_duration)
            clip = _fit_center(clip, canvas.width, canvas.height).with_start(start)

            effects = []
            if idx > 0 and transition > 0:
                effects.append(vfx.CrossFadeIn(transition).copy())
            if idx < len(segments) - 1 and transition > 0:
                effects.append(vfx.CrossFadeOut(transition).copy())
            if effects:
                clip = clip.with_effects(effects)
            video_layers.append(clip)

            if seg.comment:
                text_kwargs = {
                    "text": seg.comment,
                    "font_size": job.subtitle.font_size,
                    "color": job.subtitle.color,
                    "stroke_color": job.subtitle.stroke_color,
                    "stroke_width": job.subtitle.stroke_width,
                    "margin": (0, 0, 0, max(0, job.subtitle.bottom_margin)),
                    "duration": segment_duration,
                }
                if job.subtitle.font_path and Path(job.subtitle.font_path).exists():
                    text_kwargs["font"] = job.subtitle.font_path
                subtitle = (
                    TextClip(**text_kwargs)
                    .with_start(start)
                    .with_position(("center", "bottom"))
                )
                subtitle_layers.append(subtitle)

            if voice_src:
                available = max(0.0, segment_duration - voice_offset)
                voice_end = min(voice_src.duration, available)
                if voice_end > 0:
                    voice_clip = voice_src.subclipped(0, voice_end).with_start(start + voice_offset)
                    if job.audio.voice_volume != 1.0:
                        voice_clip = voice_clip.with_volume_scaled(job.audio.voice_volume)
                    audio_tracks.append(voice_clip)

            cursor += segment_duration

        total_duration = sum(durations) - transition * max(0, len(durations) - 1)
        total_duration = max(total_duration, 0.1)

        bg = ColorClip(
            size=(canvas.width, canvas.height),
            color=canvas.bg_color,
            duration=total_duration,
        )
        final = CompositeVideoClip([bg, *video_layers, *subtitle_layers])

        if bgm_path and bgm_path.exists():
            bgm_src = AudioFileClip(str(bgm_path))
            opened_audio_sources.append(bgm_src)
            bgm_end = min(total_duration, bgm_src.duration)
            if bgm_end > 0:
                bgm = bgm_src.subclipped(0, bgm_end)
                if job.audio.bgm_volume != 1.0:
                    bgm = bgm.with_volume_scaled(job.audio.bgm_volume)
                audio_tracks.insert(0, bgm)

        if audio_tracks:
            final = final.with_audio(CompositeAudioClip(audio_tracks))

        output_path.parent.mkdir(parents=True, exist_ok=True)
        final.write_videofile(
            str(output_path),
            fps=job.output.fps,
            codec="libx264",
            pixel_format="yuv420p",
            audio_codec="aac",
            ffmpeg_params=["-preset", "veryfast"],
        )
        final.close()
        return output_path
    finally:
        for audio in opened_audio_sources:
            try:
                audio.close()
            except Exception:
                pass
