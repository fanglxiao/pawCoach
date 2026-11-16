"""PawCoach 命令行入口。

子命令（见 docs/CodePlan_detail.md）：
- probe   : 打印视频时长 / fps / 帧数 / 是否含音轨（步骤 A3）
- analyze : 视频 → JSON → 教练建议 全链路（步骤 A9）

analyze 的编排（读 meta → video/pose/audio/reward → align → coach → 落库 + 写 JSON）：
阶段 A 的 pose/audio 用 stub，B 阶段逐步换成真实现，编排代码不变。
"""

from __future__ import annotations

import argparse
from pathlib import Path


def _cmd_probe(args: argparse.Namespace) -> None:
    from pawcoach.video.probe import load_video

    info = load_video(args.path)
    print(
        f"duration={info.duration:.1f}s, fps={info.fps}, frames={info.n_frames}, "
        f"size={info.width}x{info.height}, has_audio={info.has_audio}"
    )


def _cmd_analyze(args: argparse.Namespace) -> None:
    from pawcoach import store
    from pawcoach.audio.stub import StubAudioExtractor
    from pawcoach.coach.claude import ClaudeCoach
    from pawcoach.events.align import align
    from pawcoach.pose.stub import StubPoseExtractor
    from pawcoach.reward.from_taps import TapRewardExtractor
    from pawcoach.schema import (
        AnalysisResult,
        MetaInfo,
        Quality,
        Summary,
        load_meta,
        to_json,
    )
    from pawcoach.video.probe import load_video

    path = Path(args.path)
    video_id = path.stem

    # 1) 视频信息
    video = load_video(path)

    # 2) meta（可选；不存在则用空 MetaInfo）
    meta_path = path.with_name(f"{video_id}.meta.json")
    meta = load_meta(meta_path) if meta_path.exists() else MetaInfo()

    # 3) 三条流水线（阶段 A 用 stub，B 阶段换成真实现，编排不变）
    pose = StubPoseExtractor().extract(video)
    audio = StubAudioExtractor().extract(video, meta)
    rewards = TapRewardExtractor().extract(meta, audio)

    # 4) 对齐 → 轮次
    trials, unpaired = align(pose, audio, rewards, meta)

    # 5) 聚合指标
    holds = [t.hold for t in trials if t.hold is not None]
    successes = [t for t in trials if t.reward_t is not None]
    confs = [s.conf for s in pose]
    result = AnalysisResult(
        video_id=video_id,
        quality=Quality(
            dog_visible_ratio=1.0,
            audio_ok=video.has_audio,
            pose_conf_mean=(sum(confs) / len(confs)) if confs else 0.0,
        ),
        trials=trials,
        summary=Summary(
            trials=len(trials),
            success_rate=(len(successes) / len(trials)) if trials else None,
            median_hold=_median(holds),
        ),
        unpaired=unpaired,
    )

    # 6) 教练建议（ClaudeCoach：无 key / 超时兜底到 TemplateCoach）
    result.coach = ClaudeCoach().plan(result, [])

    # 7) 落库（数据飞轮从 A9 埋点）
    store.save_result(result)

    # 8) 写 JSON + 打印建议
    out = Path(args.output or f"results/{video_id}.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(to_json(result), encoding="utf-8")

    print(result.coach)
    print(f"\n[结果已写入 {out}]")
    print("[已落库 data/pawcoach.db]")


def _median(values: list[float]) -> float | None:
    """中位数；空列表返回 None。"""
    if not values:
        return None
    ordered = sorted(values)
    n = len(ordered)
    mid = n // 2
    if n % 2:
        return ordered[mid]
    return round((ordered[mid - 1] + ordered[mid]) / 2, 2)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="pawcoach")
    sub = parser.add_subparsers(dest="command", required=True)

    p_probe = sub.add_parser("probe", help="打印视频信息")
    p_probe.add_argument("path", help="视频文件路径")
    p_probe.set_defaults(func=_cmd_probe)

    p_analyze = sub.add_parser("analyze", help="分析训练视频并生成教练建议")
    p_analyze.add_argument("path", help="视频文件路径")
    p_analyze.add_argument(
        "-o", "--output",
        help="结果 JSON 输出路径（默认 results/<video_id>.json）",
    )
    p_analyze.set_defaults(func=_cmd_analyze)

    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
