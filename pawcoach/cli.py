"""PawCoach 命令行入口。

子命令（见 docs/CodePlan_detail.md）：
- probe     : 打印视频时长 / fps / 帧数 / 是否含音轨 / 编码 / 旋转 / 是否变帧率（步骤 A3、A10）
- normalize : 把手机视频标准化为 H.264 + 固定帧率 + 方向摆正（步骤 A10）
- analyze   : 视频 → JSON → 教练建议 全链路（步骤 A9）；分析前先自动标准化（步骤 A10）

analyze 的编排（标准化 → 读 meta → video/pose/audio/reward → align → coach → 落库 + 写 JSON）：
阶段 A 的 pose/audio 用 stub，B 阶段逐步换成真实现，编排代码不变。
"""

from __future__ import annotations

import argparse
from pathlib import Path

NORMALIZED_DIR = "data/normalized"


def _cmd_probe(args: argparse.Namespace) -> None:
    from pawcoach.video.probe import load_video

    info = load_video(args.path)
    print(
        f"duration={info.duration:.1f}s, fps={info.fps}, frames={info.n_frames}, "
        f"size={info.width}x{info.height}, has_audio={info.has_audio}, "
        f"codec={info.codec}, rotation={info.rotation}, vfr={info.is_vfr}"
    )


def _cmd_normalize(args: argparse.Namespace) -> None:
    from pawcoach.video.normalize import normalize_video

    res = normalize_video(args.path, args.out_dir, force=args.force)
    if res.transcoded:
        print(f"已标准化：{res.path}")
        for r in res.reasons:
            print(f"  - {r}")
    else:
        print(f"已符合标准，无需转码：{res.path}")
    i = res.info
    print(
        f"duration={i.duration:.1f}s, fps={i.fps:.2f}, size={i.width}x{i.height}, "
        f"codec={i.codec}, rotation={i.rotation}, vfr={i.is_vfr}"
    )


def _make_pose_extractor():
    """姿态提取器：优先 SuperAnimal 真实现（读已缓存的 H5 + 狗框），环境不支持则回退 stub。

    两个 Python 环境（见 requirements-b.txt）：`.venv-b`（3.12）有 pandas/ultralytics/deeplabcut，
    `.venv`（3.13）只有 numpy/pydantic/httpx。真实现读 H5 需要 pandas，所以在 `.venv` 里回退 stub。
    姿态推理和狗检测只读缓存（`run_if_missing=False`），缓存缺失时明确报错，不在 analyze 里隐式跑模型。
    """
    try:
        import pandas  # noqa: F401  读 SuperAnimal H5 需要
    except ImportError:
        from pawcoach.pose.stub import StubPoseExtractor

        return StubPoseExtractor(), "stub（当前环境缺 pandas，姿态整段占位）"

    from pawcoach.pose.superanimal import SuperAnimalPoseExtractor

    return SuperAnimalPoseExtractor(run_if_missing=False, use_detection=True), "superanimal"


def _cmd_analyze(args: argparse.Namespace) -> None:
    from pawcoach import store
    from pawcoach.audio.asr import AsrAudioExtractor
    from pawcoach.coach.claude import ClaudeCoach
    from pawcoach.events.align import align
    from pawcoach.reward.merged import MergedRewardExtractor
    from pawcoach.schema import (
        AnalysisResult,
        MetaInfo,
        Quality,
        Summary,
        load_meta,
        to_json,
    )
    from pawcoach.video.normalize import normalize_video
    from pawcoach.video.probe import load_video

    path = Path(args.path)
    # video_id 与 meta 按原始文件名定，标准化产物的文件名不能影响它们
    video_id = path.stem
    meta_path = path.with_name(f"{video_id}.meta.json")

    # 1) 标准化（手机 HEVC / 竖屏旋转 / 变帧率 → H.264 固定帧率摆正），已符合标准则原样复用
    norm = normalize_video(path, NORMALIZED_DIR)
    if norm.transcoded:
        print(f"[已标准化：{'；'.join(norm.reasons)} → {norm.path}]")
    video = load_video(norm.path)

    # 2) meta（可选；不存在则用空 MetaInfo）
    meta = load_meta(meta_path) if meta_path.exists() else MetaInfo()

    # 3) 三条流水线（阶段 B：姿态换真实现；环境缺 pandas 时回退 stub，编排不变）
    pose_extractor, pose_impl = _make_pose_extractor()
    print(f"[姿态：{pose_impl}]")
    pose = pose_extractor.extract(video)
    audio = AsrAudioExtractor().extract(video, meta)
    rewards = MergedRewardExtractor().extract(meta, audio)

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

    p_norm = sub.add_parser("normalize", help="把手机视频标准化为 H.264 + 固定帧率 + 方向摆正")
    p_norm.add_argument("path", help="视频文件路径")
    p_norm.add_argument("--out-dir", default=NORMALIZED_DIR, help=f"输出目录（默认 {NORMALIZED_DIR}）")
    p_norm.add_argument("--force", action="store_true", help="即使已符合标准也强制转码")
    p_norm.set_defaults(func=_cmd_normalize)

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
