from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class NarrationSpec:
    comment: str = ""
    voice_url: Optional[str] = None


@dataclass
class NodeSpec:
    image_url: str
    narrations: list[NarrationSpec] = field(default_factory=list)


@dataclass
class GroupSpec:
    group_id: str
    original: NodeSpec
    effects: list[NodeSpec]


@dataclass
class CanvasSpec:
    width: int = 1440
    height: int = 2560
    bg_color: tuple[int, int, int] = (0, 0, 0)


@dataclass
class OutputSpec:
    filename: str = "output.mp4"
    fps: int = 30
    canvas: CanvasSpec = field(default_factory=CanvasSpec)


@dataclass
class AudioSpec:
    bgm_url: Optional[str] = None
    bgm_volume: float = 0.25
    voice_volume: float = 1.0


@dataclass
class SubtitleSpec:
    font_path: Optional[str] = "C:/Windows/Fonts/msyh.ttc"
    font_size: int = 72
    color: str = "white"
    stroke_color: str = "black"
    stroke_width: int = 2
    bottom_margin: int = 100


@dataclass
class TimelineSpec:
    transition_sec: float = 0.5
    default_still_sec: float = 2.0
    voice_start_offset_sec: float = 0.0


@dataclass
class JobSpec:
    job_id: str
    groups: list[GroupSpec]
    output: OutputSpec = field(default_factory=OutputSpec)
    audio: AudioSpec = field(default_factory=AudioSpec)
    subtitle: SubtitleSpec = field(default_factory=SubtitleSpec)
    timeline: TimelineSpec = field(default_factory=TimelineSpec)


@dataclass
class ResolvedSegment:
    group_id: str
    kind: str
    image_path: Path
    comment: str = ""
    voice_path: Optional[Path] = None
