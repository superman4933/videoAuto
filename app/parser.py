import json
from pathlib import Path
from typing import Any

from .models import (
    AudioSpec,
    CanvasSpec,
    GroupSpec,
    JobSpec,
    NarrationSpec,
    NodeSpec,
    OutputSpec,
    SubtitleSpec,
    TimelineSpec,
)


def _as_str(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Invalid {field_name}: expected non-empty string.")
    return value.strip()


def _parse_node(raw: dict[str, Any], field_name: str) -> NodeSpec:
    if not isinstance(raw, dict):
        raise ValueError(f"Invalid {field_name}: expected object.")
    image_url = _as_str(raw.get("image_url"), f"{field_name}.image_url")
    narrations_raw = raw.get("narrations", [])
    if not isinstance(narrations_raw, list):
        raise ValueError(f"Invalid {field_name}.narrations: expected array.")
    narrations: list[NarrationSpec] = []
    for idx, item in enumerate(narrations_raw):
        if not isinstance(item, dict):
            raise ValueError(
                f"Invalid {field_name}.narrations[{idx}]: expected object."
            )
        comment = str(item.get("comment", "")).strip()
        voice_raw = item.get("voice_url")
        voice_url = None
        if isinstance(voice_raw, str):
            voice_url = voice_raw.strip() or None
        elif voice_raw is None:
            voice_url = None
        else:
            raise ValueError(
                f"Invalid {field_name}.narrations[{idx}].voice_url: expected string or null."
            )

        # 新规则：comment 或 voice_url 任一为空，跳过该 narration（不报错）
        if not comment or not voice_url:
            continue
        narrations.append(NarrationSpec(comment=comment, voice_url=voice_url))
    return NodeSpec(image_url=image_url, narrations=narrations)


def _parse_group(raw: dict[str, Any], index: int) -> GroupSpec:
    if not isinstance(raw, dict):
        raise ValueError(f"Invalid groups[{index}]: expected object.")
    group_id = str(raw.get("group_id") or f"group-{index+1}")
    original = _parse_node(raw.get("original"), f"groups[{index}].original")
    effects_raw = raw.get("effects", [])
    if not isinstance(effects_raw, list):
        raise ValueError(f"Invalid groups[{index}].effects: expected array.")
    effects = [
        _parse_node(item, f"groups[{index}].effects[{i}]")
        for i, item in enumerate(effects_raw)
    ]
    return GroupSpec(group_id=group_id, original=original, effects=effects)


def parse_job_file(job_path: Path) -> JobSpec:
    raw = json.loads(job_path.read_text(encoding="utf-8"))

    if not isinstance(raw, dict):
        raise ValueError("Invalid job json: expected object.")

    groups_raw = raw.get("groups")
    if not isinstance(groups_raw, list) or not groups_raw:
        raise ValueError("Invalid job json: groups must be a non-empty array.")
    groups = [_parse_group(item, i) for i, item in enumerate(groups_raw)]

    output_raw = raw.get("output", {})
    canvas_raw = output_raw.get("canvas", {})
    bg_color_raw = canvas_raw.get("bg_color", [0, 0, 0])
    if not (
        isinstance(bg_color_raw, list)
        and len(bg_color_raw) == 3
        and all(isinstance(c, int) for c in bg_color_raw)
    ):
        raise ValueError("output.canvas.bg_color must be [r,g,b].")
    canvas = CanvasSpec(
        width=int(canvas_raw.get("width", 1440)),
        height=int(canvas_raw.get("height", 2560)),
        bg_color=(bg_color_raw[0], bg_color_raw[1], bg_color_raw[2]),
    )
    output = OutputSpec(
        filename=str(output_raw.get("filename", "output.mp4")),
        fps=int(output_raw.get("fps", 30)),
        canvas=canvas,
    )

    audio_raw = raw.get("audio", {})
    audio = AudioSpec(
        bgm_url=audio_raw.get("bgm_url"),
        bgm_volume=float(audio_raw.get("bgm_volume", 0.25)),
        voice_volume=float(audio_raw.get("voice_volume", 1.0)),
    )

    subtitle_raw = raw.get("subtitle", {})
    subtitle = SubtitleSpec(
        font_path=subtitle_raw.get("font_path", "C:/Windows/Fonts/msyh.ttc"),
        font_size=int(subtitle_raw.get("font_size", 72)),
        color=str(subtitle_raw.get("color", "white")),
        stroke_color=str(subtitle_raw.get("stroke_color", "black")),
        stroke_width=int(subtitle_raw.get("stroke_width", 2)),
        bottom_margin=int(subtitle_raw.get("bottom_margin", 100)),
    )

    timeline_raw = raw.get("timeline", {})
    timeline = TimelineSpec(
        transition_sec=float(timeline_raw.get("transition_sec", 0.5)),
        default_still_sec=float(timeline_raw.get("default_still_sec", 2.0)),
        voice_start_offset_sec=float(timeline_raw.get("voice_start_offset_sec", 0.0)),
    )

    return JobSpec(
        job_id=str(raw.get("job_id", job_path.stem)),
        groups=groups,
        output=output,
        audio=audio,
        subtitle=subtitle,
        timeline=timeline,
    )
