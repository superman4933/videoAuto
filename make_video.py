"""
将指定目录下的两张图片合成为 MP4 视频：
- 画布：宽 1440、高 2560，黑色背景；图片与字幕居中显示
- 每张图片显示 3 秒，转场渐变 0.5 秒
- 字幕：底部居中，「醒醒酒啊啊」，第 2 秒起持续 3 秒，与底边留边距
- 背景音乐：images/2月5日 (1).MP3；配音：y1878.wav 从第 1 秒开始

使用 MoviePy 2.x：vfx.CrossFadeIn/CrossFadeOut + CompositeVideoClip。
"""

from pathlib import Path

from moviepy import (
    AudioFileClip,
    ColorClip,
    CompositeVideoClip,
    CompositeAudioClip,
    ImageClip,
    TextClip,
    vfx,
)


def main():
    # 项目根目录（脚本所在目录即 pythonProject2）
    base_dir = Path(__file__).resolve().parent
    img_dir = base_dir / "images" / "001" / "原图"

    image_names = ["任务1_原图.jpg", "image.png"]
    image_paths = [img_dir / name for name in image_names]

    for p in image_paths:
        if not p.exists():
            raise FileNotFoundError(f"图片不存在: {p}")

    duration_per_image = 2  # 秒
    transition_duration = 0.5  # 秒
    canvas_w, canvas_h = 1440, 2560  # 固定画布，黑色背景

    # 黑色背景：按图片段总时长设置，避免拉长最终时间轴
    sequence_duration = duration_per_image * len(image_paths) - transition_duration * (len(image_paths) - 1)
    black_bg = ColorClip(size=(canvas_w, canvas_h), color=(0, 0, 0), duration=sequence_duration)

    def fit_center(clip, w, h):
        """将片段缩放到 (w,h) 内保持比例，并居中。"""
        scale = min(w / clip.w, h / clip.h)
        nw, nh = int(clip.w * scale), int(clip.h * scale)
        if nw % 2 != 0:
            nw -= 1
        if nh % 2 != 0:
            nh -= 1
        return clip.resized((nw, nh)).with_position("center")

    # 第一张图：3 秒，末尾 0.5 秒淡出，适配画布并居中
    clip1 = (
        ImageClip(str(image_paths[0]), duration=duration_per_image)
        .with_effects([vfx.CrossFadeOut(transition_duration).copy()])
    )
    clip1 = fit_center(clip1, canvas_w, canvas_h)
    # 第二张图：3 秒，开头 0.5 秒淡入，从 2.5 秒开始，适配画布并居中
    clip2 = (
        ImageClip(str(image_paths[1]), duration=duration_per_image)
        .with_effects([vfx.CrossFadeIn(transition_duration).copy()])
        .with_start(duration_per_image - transition_duration)
    )
    clip2 = fit_center(clip2, canvas_w, canvas_h)

    # 字幕：画布底部居中，与底边留 70px 边距，整行完整显示
    font_path = "C:/Windows/Fonts/msyh.ttc"
    if not Path(font_path).exists():
        font_path = "C:/Windows/Fonts/simhei.ttf"
    text_clip = TextClip(
        text="123aB!@你好",
        font=font_path,
        font_size=72,
        color="white",
        stroke_color="black",
        stroke_width=2,
        margin=(0, 0, 0, 100),
        duration=3,
    ).with_start(2)
    # 使用底部对齐 + 下边透明留白，避免字体度量差异导致贴底和裁剪
    text_clip = text_clip.with_position(("center", "bottom"))

    final = CompositeVideoClip([black_bg, clip1, clip2, text_clip])
    output_path = base_dir / "output1.mp4"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # 背景音乐 + 配音（配音从第 1 秒开始）
    duration = final.duration
    bgm_path = base_dir / "images" / "2月5日 (1).MP3"
    voice_path = base_dir /  "images" /"y1878.wav"
    audio_clips = []
    if bgm_path.exists():
        bgm_clip = AudioFileClip(str(bgm_path))
        bgm_end = min(duration, bgm_clip.duration)
        bgm = bgm_clip.subclipped(0, bgm_end)
        audio_clips.append(bgm)
    if voice_path.exists():
        voice_clip = AudioFileClip(str(voice_path))
        voice_end = min(max(0, duration - 1), voice_clip.duration)
        if voice_end > 0:
            voice = voice_clip.subclipped(0, voice_end).with_start(1)
            audio_clips.append(voice)
    if audio_clips:
        final = final.with_audio(CompositeAudioClip(audio_clips))

    final.write_videofile(
        str(output_path),
        fps=30,
        codec="libx264",
        pixel_format="yuv420p",
        audio_codec="aac",
        ffmpeg_params=["-preset", "veryfast"],
    )
    final.close()
    print(f"已生成视频: {output_path}")


if __name__ == "__main__":
    main()
