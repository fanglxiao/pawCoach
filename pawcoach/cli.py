"""PawCoach 命令行入口。

子命令（见 docs/CodePlan_DS.md）：
- probe : 打印视频时长 / fps / 帧数 / 是否含音轨（步骤 A3）

analyze 子命令留到步骤 A9 再接入。
"""

from __future__ import annotations

import argparse


def _cmd_probe(args: argparse.Namespace) -> None:
    from pawcoach.video.probe import load_video

    info = load_video(args.path)
    print(
        f"duration={info.duration:.1f}s, fps={info.fps}, frames={info.n_frames}, "
        f"size={info.width}x{info.height}, has_audio={info.has_audio}"
    )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="pawcoach")
    sub = parser.add_subparsers(dest="command", required=True)

    p_probe = sub.add_parser("probe", help="打印视频信息")
    p_probe.add_argument("path", help="视频文件路径")
    p_probe.set_defaults(func=_cmd_probe)

    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
