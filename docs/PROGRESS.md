# PawCoach 开发进度

> 更新时间：2026-11-16。计划全文见 [CodePlan_detail.md](CodePlan_detail.md)，每步的验收记录见 [../reports/](../reports/)。

## 当前状态

**阶段 A（骨架与全链路跑通）已完成。** 一条命令可以跑完「视频 → JSON → 教练建议 → 落库」：

```bash
python -m pawcoach.cli analyze data/raw/sample.mp4 -o results/sample.json
```

当前链路里姿态和口令仍是 stub，只有奖励打点是真实现。手机视频（HEVC、竖屏旋转、变帧率）会在分析前自动标准化。下一步是阶段 B，把姿态和口令换成真实现。

## 总览

| 阶段 | 内容 | 进度 |
|---|---|---|
| A | 骨架与全链路跑通 | 10 / 10 完成（A10 视频标准化是后加的，因目标平台是安卓和 iOS） |
| B | 换真实现（姿态、口令、奖励合并） | 0 / 8，未开始 |
| C | 判定、处方、安全 | 0 / 5，未开始 |
| D | 演示与准备 | 0 / 4，未开始 |

## 阶段 A 明细

| 步骤 | 内容 | commit | 验收结果 |
|---|---|---|---|
| A1 | 初始化环境 | `05ebbe3` | numpy、pydantic、httpx 可导入，ffmpeg 可用 |
| A2 | 项目骨架 + `schema.py` | `05ebbe3` | `AnalysisResult()` 能打印空结构 |
| A3 | `video` 模块 + `probe` 命令 | `05ebbe3` | `probe` 输出时长、fps、帧数、音轨 |
| A4 | 三个模块接口 `Protocol` | `e15410c` | 三个 Protocol 可导入 |
| A5 | 样例视频 + `meta.json` | `17bc26f` | 两个文件存在，meta 能被 pydantic 解析 |
| A6 | 三个 stub 实现 | `805c99a` | 三个 extractor 各返回 list |
| A7 | `events/align.py` 对齐 | `0d57286` | `tests/test_align.py` 2 个用例通过 |
| A8 | `coach`（Template + Claude 兜底） | `6bc88c0` | Template 返回非空，Claude 无 key 兜底不抛异常 |
| A9 | `analyze` 命令 + `store.py` 落库 | `50830a2` | 输出 JSON 含 `video_id/quality/trials/summary/unpaired/coach` |
| A10 | 视频标准化（手机 HEVC、竖屏旋转、变帧率） | 见 git log | 合成的 iPhone 风格素材转成 H.264、rotation=0、固定 30fps、方向摆正；`tests/` 共 12 个用例通过 |

A1 到 A9 的验收标准已在一次集中验证中逐项重跑，全部通过。A10 验收见 [reports/A10.md](../reports/A10.md)。

## 各模块真假状态

| 模块 | 当前实现 | 是否真实 |
|---|---|---|
| 视频读取（probe、抽帧、抽音频） | ffmpeg | 真实 |
| 视频标准化 | ffmpeg 转 H.264、固定 30fps、方向摆正；已符合标准则不转码 | 真实，只用合成素材验证过，没有真实 iPhone 或安卓视频 |
| 奖励打点 | 读 `meta.reward_taps` | 真实 |
| 事件对齐 | 纯规则 `align()` | 真实，有单测 |
| 落库 | SQLite `data/pawcoach.db` | 真实 |
| 教练建议 | `TemplateCoach` 固定文本，`ClaudeCoach` 无 key 时兜底 | 模板文本 |
| 姿态 | `StubPoseExtractor`，整段视频算一次 `sit` | **stub** |
| 口令 | `StubAudioExtractor`，硬编码一组 cue、marker、release | **stub** |

## 真实视频验证

用 B 站一段真实狗视频跑了一遍 `analyze`（柯基坐下教学视频，60.5 秒，852x480）。

- 流水线能处理真实视频：读取规格、检测音轨、对齐、出 JSON、落库都没出错。
- 结果里的 `hold=60.49`、`latency=0.0`、`cue_t=0.0` 是 stub 写死的值，不是测量结果。
- 该视频是带字幕的教学视频，不是干净的「口令、坐下、保持、释放」，不适合做基线。

## 数据位置

以下路径都在 `.gitignore` 中，只存在本机。

| 数据 | 位置 |
|---|---|
| 合成样例视频（30 秒，无狗） | `data/raw/sample.mp4`、`data/raw/sample.meta.json` |
| 真实狗视频（B 站，仅本机验证用） | `data/raw/dog1.mp4` |
| 真实狗视频（YouTube，CC BY，供 B1 验证姿态） | `data/raw/dog2.mp4`，来源与许可记在 `data/sources.csv` |
| 分析结果 JSON | `results/sample.json`、`results/dog1.json` |
| 落库 | `data/pawcoach.db` 的 `analyses` 表，`payload` 列存完整结果 |

## 已知问题

1. `pytest` 没写进 `requirements.txt`，新环境按 requirements 安装后跑不了 A7 的测试。
2. `ClaudeCoach` 的真实 API 调用路径没验证过。本机没有 `ANTHROPIC_API_KEY`，只验证了兜底分支。
3. `yt-dlp` 只装在 `.venv` 里，没有写进 requirements。
4. 网络：这台机器直连不了 GitHub、HuggingFace、Wikimedia Commons、Google，国内站点（B 站、清华 PyPI 镜像）可直连。国外站点要走本机代理 `127.0.0.1:7892`（macOS 系统代理已开启，HTTP、HTTPS、SOCKS 同一端口），但终端环境变量没有设代理，命令默认不会走它，需要显式指定，例如 `curl -x http://127.0.0.1:7892`、`yt-dlp --proxy http://127.0.0.1:7892`。已验证经代理可访问 GitHub、HuggingFace、Wikimedia Commons、Google、YouTube。代理软件没启动时国外站点会超时，所以 B1 下载 SuperAnimal 权重前要先确认代理在运行。
5. 真实视频还没有一段是干净的「口令、坐下、保持、释放」完整过程。`dog1.mp4` 带字幕和讲解；`dog2.mp4`（比利时牧羊犬幼犬，单镜头，17.5 秒）是手势引导坐下，没有保持和释放，只适合验证姿态识别，保持时长没有真值可对。Wikimedia Commons 里没找到坐下训练类视频。
6. 复核字段 `reviewer_correction`、`risk_flag` 等只在表里预留，还没有写入逻辑。
7. 视频标准化只用合成素材验证过，没有真实 iPhone 或安卓视频。HDR（10-bit）、杜比视界、实况照片等情况没处理。标准化会把音轨压成 16kHz 单声道，原始音质不保留。
8. `data/normalized/` 里的标准化产物不会自动清理，会随分析量增长。

## 下一步

按计划做阶段 B。先做 B1（SuperAnimal 安装 + 关键点推理），它是 B 阶段唯一的环境风险点。
