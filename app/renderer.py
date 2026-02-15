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

INTRA_GROUP_CUE_DELAY_SEC = 0.8


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
    cover_path: Path | None = None,
) -> Path:
    if not segments:
        raise ValueError("No segments to render.")

    canvas = job.output.canvas
    transition = max(0.0, job.timeline.transition_sec)
    default_still = max(0.1, job.timeline.default_still_sec)
    voice_offset = max(0.0, job.timeline.voice_start_offset_sec)
    # Subtitle style scales with canvas size (base design: 1440x2560)
    subtitle_scale = min(canvas.width / 1440, canvas.height / 2560)
    scaled_font_size = max(24, int(round(job.subtitle.font_size * subtitle_scale)))
    scaled_stroke_width = max(1, int(round(job.subtitle.stroke_width * subtitle_scale)))
    scaled_bottom_margin = max(48, int(round(job.subtitle.bottom_margin * subtitle_scale)))
    # Extra pad reduces glyph-bottom clipping risk on some fonts/renderers.
    scaled_subtitle_safe_pad = max(
        8, int(round(scaled_font_size * 0.2)) + scaled_stroke_width
    )

    def _slide_out_left_sync(clip, duration: float):
        """Slide current clip out to left during its last `duration` seconds."""
        if duration <= 0:
            return clip
        base_x = (canvas.width - clip.w) / 2
        base_y = (canvas.height - clip.h) / 2
        hold_until = max(0.0, clip.duration - duration)

        def _pos(t: float):
            if t <= hold_until:
                return (base_x, base_y)
            progress = min(1.0, max(0.0, (t - hold_until) / duration))
            x = base_x - progress * (base_x + clip.w)
            return (x, base_y)

        return clip.with_position(_pos)

    def _slide_in_right_sync(clip, duration: float):
        """Slide current clip in from right during its first `duration` seconds."""
        if duration <= 0:
            return clip
        base_x = (canvas.width - clip.w) / 2
        base_y = (canvas.height - clip.h) / 2
        start_x = canvas.width

        def _pos(t: float):
            progress = min(1.0, max(0.0, t / duration))
            x = start_x + (base_x - start_x) * progress
            return (x, base_y)

        return clip.with_position(_pos)

    opened_audio_sources: list[AudioFileClip] = []
    video_layers = []
    subtitle_layers = []
    audio_tracks = []

    cursor = 0.0
    durations: list[float] = []
    starts: list[float] = []
    subtitle_segment_indices: list[int] = []
    subtitle_start_times: dict[int, float] = {}
    subtitle_end_times: dict[int, float] = {}
    max_visual_voice_end = 0.0

    try:
        for idx, seg in enumerate(segments):
            is_group_first = idx == 0 or seg.group_id != segments[idx - 1].group_id
            segment_voice_offset = (
                voice_offset if is_group_first else INTRA_GROUP_CUE_DELAY_SEC
            )
            voice_src = None
            voice_duration = 0.0
            voice_end = 0.0
            if seg.voice_path and seg.voice_path.exists():
                voice_src = AudioFileClip(str(seg.voice_path))
                opened_audio_sources.append(voice_src)
                voice_duration = voice_src.duration

            segment_duration = max(default_still, voice_duration + segment_voice_offset)
            # Cross dissolve: overlap next clip by `transition` seconds.
            start = cursor if idx == 0 else cursor - transition
            starts.append(start)
            durations.append(segment_duration)

            clip = ImageClip(str(seg.image_path), duration=segment_duration)
            clip = _fit_center(clip, canvas.width, canvas.height).with_start(start)
            max_visual_voice_end = max(max_visual_voice_end, start + segment_duration)

            if idx > 0 and transition > 0:
                prev_group_id = segments[idx - 1].group_id
                curr_group_id = seg.group_id
                is_group_boundary = prev_group_id != curr_group_id

                if is_group_boundary:
                    # Between groups: sync both motions in same transition window.
                    video_layers[-1] = _slide_out_left_sync(video_layers[-1], transition)
                    clip = _slide_in_right_sync(clip, transition)
                else:
                    # Inside same group: keep current cross dissolve transition.
                    clip = clip.with_effects([vfx.CrossFadeIn(transition).copy()])
            video_layers.append(clip)

            if voice_src:
                available = max(0.0, segment_duration - segment_voice_offset)
                voice_end = min(voice_src.duration, available)

            if seg.comment:
                # Subtitle duration rules:
                # - with voice: subtitle starts with voice and follows voice_end
                # - without voice: follow full segment duration
                # - always end a bit earlier to avoid overlap flash
                subtitle_start = start + segment_voice_offset if voice_src else start
                raw_subtitle_duration = voice_end if voice_src else segment_duration
                subtitle_duration = min(
                    segment_duration,
                    max(0.05, raw_subtitle_duration - 0.05),
                )
                text_kwargs = {
                    "text": seg.comment,
                    "font_size": scaled_font_size,
                    "color": job.subtitle.color,
                    "stroke_color": job.subtitle.stroke_color,
                    "stroke_width": scaled_stroke_width,
                    "margin": (0, 0, 0, scaled_subtitle_safe_pad),
                    "duration": subtitle_duration,
                }
                if job.subtitle.font_path and Path(job.subtitle.font_path).exists():
                    text_kwargs["font"] = job.subtitle.font_path
                subtitle = TextClip(**text_kwargs).with_start(subtitle_start)
                x_left = (canvas.width - subtitle.w) / 2
                y_top = canvas.height - scaled_bottom_margin - subtitle.h
                subtitle = subtitle.with_position((max(0, x_left), max(0, y_top)))
                subtitle_layers.append(subtitle)
                subtitle_segment_indices.append(idx)
                subtitle_start_times[idx] = subtitle_start
                subtitle_end_times[idx] = subtitle_start + subtitle_duration

            if voice_src:
                if voice_end > 0:
                    voice_clip = voice_src.subclipped(0, voice_end).with_start(
                        start + segment_voice_offset
                    )
                    if job.audio.voice_volume != 1.0:
                        voice_clip = voice_clip.with_volume_scaled(job.audio.voice_volume)
                    audio_tracks.append(voice_clip)
                    max_visual_voice_end = max(
                        max_visual_voice_end, start + segment_voice_offset + voice_end
                    )

            # Keep overlap timing consistent at every boundary.
            # First clip advances by full duration; following clips advance by
            # "duration - transition" because their starts are shifted earlier.
            if idx == 0:
                cursor += segment_duration
            else:
                cursor += max(0.0, segment_duration - transition)

        # Hard-cut subtitle before next segment start to avoid adjacent overlap.
        subtitle_gap = 0.05
        for layer_idx, subtitle in enumerate(subtitle_layers):
            seg_idx = subtitle_segment_indices[layer_idx]
            if seg_idx + 1 >= len(starts):
                continue
            original_end = subtitle_end_times.get(seg_idx)
            if original_end is None:
                continue
            capped_end = min(original_end, starts[seg_idx + 1] - subtitle_gap)
            subtitle_start = subtitle_start_times.get(seg_idx, starts[seg_idx])
            new_duration = max(0.05, capped_end - subtitle_start)
            subtitle_layers[layer_idx] = subtitle.with_duration(new_duration)
            subtitle_end_times[seg_idx] = subtitle_start + new_duration

        # Trim by the actual latest content end (visual/subtitle/voice).
        subtitle_max_end = max(subtitle_end_times.values(), default=0.0)
        total_duration = max(max_visual_voice_end, subtitle_max_end, 0.1)

        bg = ColorClip(
            size=(canvas.width, canvas.height),
            color=canvas.bg_color,
            duration=total_duration,
        )
        first_frame_cover_layers = []
        if cover_path and cover_path.exists():
            cover_frame_duration = max(1.0 / max(1, job.output.fps), 0.04)
            cover_clip = ImageClip(str(cover_path), duration=cover_frame_duration)
            cover_clip = _fit_center(cover_clip, canvas.width, canvas.height).with_start(0)
            # Put cover on top so frame-0 preview matches requested thumbnail.
            first_frame_cover_layers.append(cover_clip)

        final = CompositeVideoClip(
            [bg, *video_layers, *subtitle_layers, *first_frame_cover_layers]
        )

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
            # ffmpeg_params=["-preset", "veryfast"],
            ffmpeg_params=["-preset", "ultrafast"],
        )
        final.close()
        return output_path
    finally:
        for audio in opened_audio_sources:
            try:
                audio.close()
            except Exception:
                pass
