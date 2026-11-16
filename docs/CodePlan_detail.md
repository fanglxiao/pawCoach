# PawCoach MVP 开发计划（详细版 · 跑通优先 · 按工时推进）

> 依据：[research.md](research.md)、[pet-training-agent-technical-resources.md](pet-training-agent-technical-resources.md)、[datasets-and-papers.md](datasets-and-papers.md)。
> 定位：Hackathon MVP，只做「坐下 + 等待保持（Sit-Stay）」一个场景，只用公开/可授权数据。
>
> **首要目标：把「视频 → JSON → 教练建议」这条链路跑通。准确率是跑通之后的迭代目标，不是挡路的门槛。**
>
> **推进方式：按工时，不按天。** 每一步标注预计工时（⏱），可按碎片时间任意拆做；步骤编号即执行顺序，做完打勾。全部步骤合计约 **40～55 工时**。

---

## 0. 总原则

1. **跑通优先，调准靠后。** 每个步骤的验收 =「一条命令能跑 + 一个可见产出」，而不是一个准确率数字。准确率只做「记录基线」写进 `reports/`，跑通后再迭代。
2. **接口先行，实现可替换。** 每个模块先定义接口（Python `Protocol`），首版实现可以是 stub（返回假数据/空数据）。换真实现时**不改编排代码**。
3. **每次替换实现后，端到端必须仍能跑通。** 回归验证就是那一条命令，不做第二套东西。
4. **宁可少报、不可猜。** 置信度门控是贯穿的硬约束，但它是 C 阶段的迭代项，不是 A 阶段的卡关项——先让数据流下去，再让「看不清」正确地变成「看不清」。

**一句话**：做完 A 阶段，你要能对一个真实视频跑出完整的 JSON 和建议文本，哪怕里面的姿态是假的、口令是空的。之后每步只换一个组件。

---

## 1. 目标与最终形态

### 1.1 一条命令

```bash
python -m pawcoach.cli analyze data/raw/<video_id>.mp4 -o results/<video_id>.json
```

输入：`data/raw/<video_id>.mp4` + 可选 `data/raw/<video_id>.meta.json`（用户标注：口令词、手动打点的奖励时刻）。

```json
// data/raw/sample.meta.json —— 用户录视频时/上传时填写的元信息
{
  "cues": ["坐"],                          // 训练口令词
  "marker_words": ["好", "对"],             // 标记词
  "release_words": ["可以了", "走"],         // 释放词
  "reward_taps": [3.2, 8.1]                 // 用户手动打点的奖励时刻（秒）
}
```

输出：`results/<video_id>.json`（见 §1.2 schema）+ 一段可读的教练建议文本。

### 1.2 统一数据结构（`pawcoach/schema.py`，A 阶段就定死）

这是全链路唯一的「合约」。所有模块都往这套结构里填，所有验收都检查这套结构是否字段齐全、类型正确。

```python
from dataclasses import dataclass, field, asdict
from typing import Literal, Optional
import json

PoseLabel = Literal["sit", "stand", "down", "unclear"]

@dataclass
class PoseSegment:
    t_start: float
    t_end: float
    label: PoseLabel
    conf: float                     # 0~1，越低越不可信

@dataclass
class AudioEvent:
    word: str                       # 命中的词（坐/好/可以了/sit/…）
    t_start: float
    t_end: float
    kind: Literal["cue", "marker", "release", "other"]

@dataclass
class RewardEvent:
    t: float
    source: Literal["tap", "marker", "visual"]   # 来源：用户打点/标记词/视觉

@dataclass
class Trial:
    cue_t: Optional[float] = None
    sit_start: Optional[float] = None
    sit_end: Optional[float] = None
    ended_by: Optional[Literal["release", "stand_up", "unknown"]] = None
    reward_t: Optional[float] = None
    latency: Optional[float] = None             # 反应延迟
    hold: Optional[float] = None                # 保持时长
    reward_delay: Optional[float] = None        # 奖励延迟
    conf: float = 0.0                           # 本轮整体置信度

@dataclass
class Quality:
    dog_visible_ratio: float = 0.0
    audio_ok: bool = False
    pose_conf_mean: float = 0.0

@dataclass
class Summary:
    trials: int = 0
    success_rate: Optional[float] = None
    median_hold: Optional[float] = None

@dataclass
class AnalysisResult:
    video_id: str = ""
    dog_id: str = ""
    date: str = ""
    quality: Quality = field(default_factory=Quality)
    trials: list[Trial] = field(default_factory=list)
    summary: Summary = field(default_factory=Summary)
    unpaired: list[dict] = field(default_factory=list)  # 无法配对的事件，作反馈素材
    coach: str = ""                                  # 教练建议文本

def to_json(result: AnalysisResult) -> str:
    return json.dumps(asdict(result), ensure_ascii=False, indent=2)
```

### 1.3 三条流水线（架构不变，但每条的「跑通版」先用 stub）

```
① 状态测量：视频 → PoseSegment[]（狗姿态时间线） + AudioEvent[]（口令） + RewardEvent[]
② 规则判定：三段事件 → Trial[] + Summary（纯规则，无模型）
③ 处方生成：Trial[] + 历史 + SOP → 教练建议文本
```

大模型只出现在 ③，永远「读数字」不看视频（K9-Bench 依据，见 datasets-and-papers.md §1）。① 里的每个提取器都有接口，跑通版先用 stub。

---

## 2. 工作方式（可管理）

**每个步骤固定五步**，做完才进下一个：

1. **开工前**：在 `reports/<阶段><步骤>.md` 顶部写一行「验收命令」。
2. **实现**：只改本步骤负责的模块，接口不动。
3. **验收**：跑验收命令，看产出是否可见、字段是否齐全。
4. **记录**：把基线的那个数字写进报告（难看也记）。
5. **回归**：跑一遍 `analyze`，确认端到端仍通；再 commit。

**报告模板**（每份 `reports/` 都是这个结构）：

```markdown
# B2 姿态规则
- 验收命令：python -m pawcoach.cli analyze data/raw/sample.mp4 -o results/sample.json
- 验收结果：通过 / 未通过
- 基线指标：逐帧准确率 X%，hold 误差中位数 Ys（n=10）
- 遗留问题：……
- 下一步（调准）：……
```

**Definition of Done**（每个步骤都满足才算完）：
- [ ] 验收命令跑通、产出可见
- [ ] `results/*.json` 字段齐全、类型正确
- [ ] 基线写进 `reports/`
- [ ] 端到端回归通过（`analyze` 一条命令）
- [ ] git commit

**工时记录**：每个步骤做完，在步骤标题旁把「预计工时 / 实际工时」写回，方便后续排期——这正是本计划不用「天」的原因。

---

## 3. 步骤清单

> 编号 = 执行顺序。⏱ = 预计工时（单人）。「验收」= 可观察产出；「记录」= 基线数字（只记，不卡）。

### 阶段 A：骨架与全链路跑通（合计约 12～16 工时）

> 目标：一条命令跑完「视频 → JSON → 建议」。所有组件「能跑就行」，之后每步只换一个。

| 步骤 | 内容 | ⏱ |
|---|---|---|
| **A1** | 初始化环境 | 1～1.5h |
| **A2** | 项目骨架 + `schema.py` | 1～1.5h |
| **A3** | `video` 模块 + `probe` 命令 | 1.5～2h |
| **A4** | 三个模块接口 `Protocol` | 0.5h |
| **A5** | 准备样例视频 + `meta.json` | 0.5h |
| **A6** | 三个 stub 实现 | 1h |
| **A7** | `events/align.py` 对齐 | 2h |
| **A8** | `coach`（Template + Claude 兜底） | 1.5h |
| **A9** | `analyze` 命令 + `store.py` 落库 | 1.5～2h |

#### A1 · 初始化环境（⏱ 1～1.5h）

```bash
cd /Users/fanglingxiao/GitProjects/hongqiao-hackson/pawCoach
python -m venv .venv && source .venv/bin/activate
pip install --upgrade pip
pip install numpy pydantic httpx      # 阶段 A 只装这些，轻装跑通
# 确认 ffmpeg 可用
ffmpeg -version || brew install ffmpeg
```

依赖分两档，**别第一天就卡在重依赖上**：
- **阶段 A 必装**：`numpy`、`pydantic`、`httpx`（Claude API）。
- **阶段 B 再装**：`torch`、`ultralytics`（YOLO）、`deeplabcut`/SuperAnimal、`funasr`、`openai-whisper`。**这是环境安装的主要风险点，各自在 B 阶段由负责的人单独解决，不阻塞 A。**

**验收**：`python -c "import numpy, pydantic, httpx"` 无报错；`ffmpeg -version` 有输出。

#### A2 · 项目骨架 + schema（⏱ 1～1.5h）

- 建目录（见 §6），写 `pyproject.toml` 或 `requirements.txt`（分 A/B 两档）。
- 写 `pawcoach/schema.py`（§1.2 全文，一字不差先落地）。
- 若仓库未初始化：`git init && git add -A && git commit -m "chore: 项目骨架与 schema"`。

**验收**：`python -c "from pawcoach.schema import AnalysisResult; print(AnalysisResult())"` 能打印空结构。

#### A3 · video 模块 + probe 命令（⏱ 1.5～2h）

写 `pawcoach/video/`：
- `load_video(path) -> VideoInfo`：时长、fps、是否含音轨（用 `ffmpeg -i` 拿信息，**不要一开始就上 opencv 读帧**）。
- `extract_frames(path, out_dir, fps=10)`：ffmpeg 抽帧。
- `extract_audio(path, out_wav)`：16kHz 单声道 wav。
- 写 `pawcoach/cli.py`，注册子命令 `probe`：打印时长/fps/帧数/是否含音轨。

**验收**：
```bash
source .venv/bin/activate
python -m pawcoach.cli probe data/raw/sample.mp4
# 期望看到：duration=42.3s, fps=30, frames=423, has_audio=True
```

**跑不通**：ffmpeg 未装 → `brew install ffmpeg`；依赖冲突 → 只留 `numpy`+`pydantic`，其余用 `subprocess` 调命令。

#### A4 · 三个模块接口（⏱ 0.5h）

定义 `Protocol`，stub 和真实现都实现它：

```python
# pawcoach/pose/base.py
class PoseExtractor(Protocol):
    def extract(self, video: VideoInfo) -> list[PoseSegment]: ...

# pawcoach/audio/base.py
class AudioExtractor(Protocol):
    def extract(self, video: VideoInfo, meta: MetaInfo) -> list[AudioEvent]: ...

# pawcoach/reward/base.py
class RewardExtractor(Protocol):
    def extract(self, meta: MetaInfo, audio: list[AudioEvent]) -> list[RewardEvent]: ...
```

**验收**：三个文件存在，`from pawcoach.pose.base import PoseExtractor` 可导入。

#### A5 · 样例视频 + meta（⏱ 0.5h）

- 放一段 20～60s 视频到 `data/raw/sample.mp4`（没有狗就先用任意一段，A 阶段只为跑通）。
- 配 `data/raw/sample.meta.json`（§1.1 结构）。

**验收**：两个文件存在，`meta.json` 能被 `pydantic` 解析。

#### A6 · 三个 stub（⏱ 1h）

- `pawcoach/pose/stub.py`：`StubPoseExtractor` 返回整段一个 `PoseSegment(0, duration, "sit", 0.5)`。
- `pawcoach/audio/stub.py`：`StubAudioExtractor` 返回空列表（或硬编码一个 cue，便于观察下游）。
- `pawcoach/reward/from_taps.py`：`TapRewardExtractor` 读 `meta.reward_taps` 转 `RewardEvent(source="tap")`（**这个从一开始就是真的**）。

**验收**：三个 extractor 各能被实例化并返回 list。

#### A7 · events/align.py（⏱ 2h）

写 `pawcoach/events/align.py`：`align(pose, audio, rewards, meta) -> (trials, unpaired)`，纯规则：

- 找每个 cue 后最近的 sit 段 → 组一轮；
- 算 `latency = sit_start - cue_t`、`hold = sit_end - sit_start`、`reward_delay = reward_t - (marker_t 或 sit 达成时刻)`；
- 无法配对的 cue/sit/reward 塞进 `unpaired`。

**验收**：写一个 `tests/test_align.py`，喂一组构造事件，断言 trials 数量、latency/hold 数值正确。

**跑不通**：先让每个事件各自成「一轮」的最低实现，不追求正确切分（正确性留给 C 阶段）。

#### A8 · coach（⏱ 1.5h）

- `pawcoach/coach/template.py`：`TemplateCoach.plan(...)` 返回固定文本（先跑通）。
- `pawcoach/coach/claude.py`：`ClaudeCoach.plan(...)` 调 Claude API；**无 key / 超时就 fallback 到 TemplateCoach，不阻塞**。
- 接口：`Coach.plan(result, history) -> str`。

**验收**：`TemplateCoach().plan(empty_result, [])` 返回非空字符串；`ClaudeCoach` 无 key 时能兜底不抛异常。

#### A9 · analyze 命令 + store（⏱ 1.5～2h）

- 写 `pawcoach/cli.py` 的 `analyze` 子命令：读 meta → video/pose/audio/reward → align → coach → 写 `results/<video_id>.json`，并打印建议文本到终端。
- 写 `pawcoach/store.py`：结果追加写进 SQLite（`data/pawcoach.db`），表结构与 schema 对应 + 预留 `reviewer_correction`/`risk_flag` 字段（见 §5）。**数据飞轮从这里就埋点。**

**验收（阶段 A 的总验收）**：
```bash
python -m pawcoach.cli analyze data/raw/sample.mp4 -o results/sample.json
# 期望：终端打印教练建议；results/sample.json 字段齐全
python -c "import json;d=json.load(open('results/sample.json'));print(set(d.keys()))"
# 期望包含：{'video_id','quality','trials','summary','unpaired','coach'}
```

> 到这里你就「跑通」了。B、C 阶段每步都是「换一个组件 + 重跑这条命令 + 记录一条基线」。

---

### 阶段 B：换真实现（合计约 14～20 工时）

> 目标：用真姿态、真口令、真奖励替换 stub。**先只做「坐/站/卧」粗判，过渡态和 drift 留给调准阶段。**

| 步骤 | 内容 | ⏱ |
|---|---|---|
| **B1** | SuperAnimal 安装 + 关键点推理 | 2～4h |
| **B2** | 姿态规则判坐/站/卧 + 时序平滑 | 2～3h |
| **B3** | 狗检测与跟踪 | 1～2h |
| **B4** | 姿态换真 + 跑通 + 记基线 | 1～2h |
| **B5** | FunASR/Whisper 安装 | 1～2h |
| **B6** | 口令关键词事件 | 1～2h |
| **B7** | 口令换真 + 跑通 + 记基线 | 1h |
| **B8** | 奖励合并（tap > marker > visual） | 1～1.5h |

#### B1 · SuperAnimal 安装 + 关键点推理（⏱ 2～4h）

- 单独解决 SuperAnimal 安装：`pip install deeplabcut`，或直接加载 HF 权重 `mwmathis/DeepLabCutModelZoo-SuperAnimal-Quadruped`。
- **这是整个 B 阶段唯一的环境风险。装不上就换 `mmpose` 的 AP-10K / APT-36K 权重**（datasets-and-papers.md §2.2 有两条现成路径）。
- 对 `data/raw/sample.mp4` 抽帧（10fps）逐帧推理，输出关键点，保存一张关键点可视化图到 `reports/`。

**验收**：`reports/pose_keypoints_sample.png` 存在，肉眼能看到关键点大致贴在狗身上。

**跑不通**：SuperAnimal 装不上/太慢 → 换 `mmpose`；连 mmpose 都不行 → 保持 stub 跳过 B2～B4，姿态线在演示里用「用户手动点选坐下起止」降级（见 §7）。

#### B2 · 姿态规则 + 平滑（⏱ 2～3h）

- 写 `pawcoach/pose/superanimal.py`：`SuperAnimalPoseExtractor` —— 逐帧取「臀/膝/肩」相对高度+角度写规则判坐/站/卧，输出 `PoseSegment[]`，每段带置信度。
- 时序平滑：滑动窗口多数投票 + 最短持续（< 0.5s 抖动丢弃）。

**验收**：对 `sample.mp4` 跑出 `PoseSegment[]`，打印的区间时长之和 ≈ 视频时长。

#### B3 · 狗检测与跟踪（⏱ 1～2h）

- `ultralytics` YOLO 的 `dog` 类 + IoU 关联，只保留主狗；狗不在画面 → `label="unclear"`。
- 若 B2 已用关键点直接推断，此步可简化：仅用检测框裁剪 + 判断「狗是否可见」。

**验收**：打印每帧主狗 bbox；狗离开画面的帧能标 `unclear`。

#### B4 · 姿态换真 + 跑通 + 记基线（⏱ 1～2h）

- 在 `analyze` 注册处把 pose 换成 `SuperAnimalPoseExtractor`（stub 保留作对照）。
- 重跑 `analyze`，肉眼核对时间轴大致对得上（不必精确）。

**验收**：
```bash
python -m pawcoach.cli analyze data/raw/sample.mp4 -o results/sample.json
# 期望：trials[].sit_start/sit_end 是合理数字（非 0~整段），hold 与肉眼看视频一致到 1s 内（粗略）
```

**记录基线（不设门槛）**：抽 10 段人工标注「坐/站/卧」时间区间，算逐帧准确率与 hold 误差，写 `reports/B4.md`。**难看也记，调准阶段再提。**

#### B5 · FunASR/Whisper 安装（⏱ 1～2h）

- 装 `funasr`（中文 Paraformer，带时间戳）与 `openai-whisper`。装不上就只留 Whisper 兜底。

**验收**：能对 `sample.mp4` 音轨跑出带时间戳的转写文本。

#### B6 · 口令关键词事件（⏱ 1～2h）

- 写 `pawcoach/audio/asr.py`：`AsrAudioExtractor` —— 转写（中文 FunASR，英文 Whisper）→ 用 `meta.cues/marker_words/release_words` 做关键词匹配 + 同义词表 → 输出 `AudioEvent[]`（词、起止、kind）。

**验收**：对带口令的样例，`AudioEvent` 的时间戳和听到口令的时刻对得上到 0.5s（粗略）。

#### B7 · 口令换真 + 跑通 + 记基线（⏱ 1h）

- `analyze` 换成 `AsrAudioExtractor`，重跑。

**验收**：
```bash
python -m pawcoach.cli analyze data/raw/sample.mp4 -o results/sample.json
# 期望：trials 里有 cue_t（来自真实音频事件，不再来自 stub）
```

**记录基线**：抽 10 段带口令视频人工标口令时刻，算召回率与时间误差，写 `reports/B7.md`。

**跑不通**：FunASR 装不上 → 只用 Whisper；连 Whisper 都不行 → 让用户在 `meta.json` 直接填口令时刻（等价于「用户打点口令」，产品仍成立）。

#### B8 · 奖励合并（⏱ 1～1.5h）

- 写 `pawcoach/reward/merged.py`：`MergedRewardExtractor`，优先级 **tap > marker > visual**。
  - 默认读 `meta.reward_taps`；
  - 某轮没有打点时用最近 `marker` 事件时间兜底，`source="marker"`；
  - （可选，时间够才做）MediaPipe Hands 判「手伸向狗头」，`source="visual"`——失败不影响任何东西。
- `analyze` 换成 `MergedRewardExtractor`。

**验收**：
```bash
python -m pawcoach.cli analyze data/raw/sample.mp4 -o results/sample.json
# 期望：trials[].reward_t 与 meta.reward_taps 对齐；没打点的轮次由 marker 兜底；reward_delay 可算
```

**记录基线**：打点对齐误差（用户打点 vs 实际递零食时刻），写 `reports/B8.md`。

---

### 阶段 C：判定 + 处方 + 安全（合计约 8～12 工时）

> 目标：让输出「可复核、安全、给得出建议」——把「跑通」升级为「可演示」。

| 步骤 | 内容 | ⏱ |
|---|---|---|
| **C1** | 置信度门控 | 2h |
| **C2** | 进度规则层 | 1.5h |
| **C3** | ClaudeCoach 升级 + RAG SOP | 2h |
| **C4** | 安全层 | 1.5h |
| **C5** | 30 用例评估 | 1～2h |

#### C1 · 置信度门控（⏱ 2h）

- 在 `align.py` 加聚合：dog 不可见 / pose 置信度低 / 音频无法辨认 → `label="unclear"` 或 `conf` 压低。
- 这些片段不参与 `summary` 指标，并在 `coach` 里说明「本段有 X 秒无法可靠判断」。

**验收**：构造一段「狗出画」的视频，跑 `analyze`，出画片段标 `unclear` 且不进 summary。

#### C2 · 进度规则层（⏱ 1.5h）

- 写 `pawcoach/coach/rules.py`（确定性、可测试、纯 Python）：
  - 最近 2 次成功率 ≥ 80% → 目标时长 +20～30%；
  - 成功率 < 50% → 回退上一档；
  - `reward_delay > 1.0s` 占比 > 30% → 本次重点改「标记时机」，时长不加；
  - 频率/时长：每次 3～5 分钟、5～10 轮（Demant 2011：每周 1～2 次优于每日）。

**验收**：`tests/test_rules.py` 覆盖每条规则的分支，全部通过。

#### C3 · ClaudeCoach 升级 + RAG SOP（⏱ 2h）

- `ClaudeCoach` 输入「本次指标 + 历史趋势 + 规则层输出 + 检索到的 Stay 分级 SOP（3s→10s→加干扰）」。
- 生成中文反馈：做得好的一点、最需改的一点、下次怎么练，**要求引用视频时间点**。
- SOP 语料先用一个 `prompts/sop.md` 文本 + 简单关键词检索（CricRAG 思路的最小实现），不上向量库。

**验收**：对一份真实 `results/*.json` 跑出建议文本，引用到具体秒数。

#### C4 · 安全层（⏱ 1.5h）

- 写 `pawcoach/coach/safety.py`（硬规则，优先于一切输出）：
  - 识别到咆哮/龇牙/扑咬/明显恐惧（夹尾缩身躲避）或打/踢/猛拉 → **不生成训练计划**，输出转介建议（Vieira de Castro 2020）。
  - MVP 先用「用户勾选 + 大模型对逐帧/音频描述的识别」做，不训情绪模型。

**验收**：喂一份「用户勾选『有打狗动作』」的 meta，`analyze` 输出转介文本而非训练计划。

#### C5 · 30 用例评估（⏱ 1～2h）

- 写 30 个情景用例（含 5 个安全用例）到 `eval/coach_cases.yaml`。
- 写 `pawcoach/cli.py` 的 `eval cases` 子命令跑一遍，记录结果。

**验收**：
```bash
python -m pawcoach.cli eval cases eval/coach_cases.yaml
# 期望：打印 30 用例结果（合理率、安全转介率），写 reports/C5.md
```

---

### 阶段 D：演示与准备（合计约 6～9 工时）

| 步骤 | 内容 | ⏱ |
|---|---|---|
| **D1** | FastAPI 后端 | 2～3h |
| **D2** | 前端三页 | 2～3h |
| **D3** | 性能优化 + 预跑 | 1～2h |
| **D4** | 比赛准备 + 彩排 | 1～2h |

#### D1 · FastAPI 后端（⏱ 2～3h）

- `app/main.py`：`POST /analyze`（上传视频 + meta）→ 后台线程跑 `analyze` → `GET /results/<id>`。
- 后台线程即可，不上消息队列。

**验收**：
```bash
uvicorn app.main:app --reload
curl -F "file=@data/raw/sample.mp4" -F "meta=@data/raw/sample.meta.json" localhost:8000/analyze
# 期望：返回 job_id，稍后 GET /results/<id> 拿到 JSON
```

#### D2 · 前端三页（⏱ 2～3h）

- `web/`：移动端网页三页——上传、本次结果（时间轴 + 指标 + 反馈 + 置信度标注）、进度曲线（简单 SVG/ECharts，不上重型框架）。

**验收**：浏览器 `localhost:8000` 上传 `sample.mp4` → 看到结果页。

#### D3 · 性能优化 + 预跑（⏱ 1～2h）

- 60s 视频 3 分钟内出结果（抽帧 10fps、模型走 CPU 也先保证能出）。
- 预跑 3～5 段演示视频的结果，现场网络不稳时直接展示。

**验收**：对 60s 视频计时，`analyze` 全流程 ≤ 3 分钟。

#### D4 · 比赛准备 + 彩排（⏱ 1～2h）

- 选 3 段效果最好的视频 + 1 段「恐惧 → 转介」安全演示。
- 一页准确率报告：B4/B7/C5 各项**基线**指标 + 数据来源 + 局限。
- 演示页/README 列出所有数据集、视频来源与许可（满足 CC BY 署名）。
- 完整彩排 2 次。

**验收**：彩排 2 次无故障。

---

## 4. 调准路线（跑通之后，按优先级排）

> 这些是**跑通之后**的迭代目标，不设截止，也不挡任何步骤。按「对演示观感影响最大」排序：

1. **奖励时机（最该做）**：`reward_delay` 是最能击中用户痛点的指标，也是竞品普遍忽略的点（教科书结论：奖励晚 2s 是最常见错误）。跑通后先把它做准。
2. **姿态过渡态与 body_drift**：识别「起身中/前移」才能算准「中断次数」和「挪了没站起来」。用关键点位移（按体长归一化）做。
3. **口令时间戳精度**：FunASR 热词 + 强制对齐，把中文短词误差从 ~0.5s 压到 ~0.2s。
4. **置信度建模**：参考 UIL-AQA（datasets-and-papers.md §3.2）的显式不确定度，把「判断不准」变成可管理的复核队列。
5. **训练阶段 SOP 知识库**：用 CricRAG 思路，检索「这只狗当前阶段该练什么」而非标准答案。
6. **DogPoseCV 分类器**：作为姿态的第二意见/伪标签源（注意：底图版权非商用、无官方划分需按犬种切分，见 datasets-and-papers.md §2.2）。

---

## 5. 数据飞轮（从 A9 就埋点）

三份调研的共识：**没有公开数据能直接训出产品模型，用户每日上传 + 训犬师复核结论就是在生产它，这份数据比模型更值钱。** MVP 最小实现（已在 A9 落地）：

- 每次结果结构化落库到 SQLite，表结构预留：`reviewer_correction`、`reviewer_agrees`、`risk_flag`、`referral_outcome`。
- 低置信度样本单独进 `data/review_queue/` 目录，比赛期间没训犬师也先攒着，赛后接人工。

---

## 6. 代码目录（规划）

```
pawCoach/
├── docs/                    # 调研与计划（含本文件）
├── data/                    # 不提交版本库
│   ├── raw/                 # 视频片段 + 同名 .meta.json
│   ├── labels/              # 人工标注 JSON
│   ├── sources.csv          # 链接/作者/许可/时间段
│   ├── review_queue/        # 低置信度样本（数据飞轮）
│   ├── annotation_guide.md
│   └── pawcoach.db          # SQLite
├── pawcoach/
│   ├── cli.py               # probe / analyze / eval 子命令
│   ├── schema.py            # §1.2 数据结构（合约）
│   ├── store.py             # SQLite 落库
│   ├── video/               # 解码、抽帧、提音频、质量检查
│   ├── pose/                # base.py + stub.py + superanimal.py
│   ├── audio/               # base.py + stub.py + asr.py
│   ├── reward/              # base.py + from_taps.py + merged.py
│   ├── events/              # align.py（对齐+置信度+指标）
│   └── coach/               # template.py + claude.py + rules.py + safety.py
├── eval/                    # coach_cases.yaml + 评估脚本
├── notebooks/
├── reports/                 # A1.md … D4.md（每步结论+基线）
├── app/                     # FastAPI
├── web/                     # 前端
├── results/                 # 每次 analyze 的 JSON 输出（不提交）
└── tests/
```

---

## 7. 风险与预案（针对「跑不起来」，不是「不准」）

| 风险 | 影响步骤 | 预案 |
|---|---|---|
| SuperAnimal / torch 装不上 | B1～B4 | 换 mmpose（AP-10K/APT-36K 权重）；再不行保持 stub，姿态走「用户手动点选坐下起止」降级 |
| FunASR 装不上 | B5～B7 | 只用 Whisper；再不行用户直接在 meta.json 填口令时刻 |
| Claude API 无 key / 超时 | A8/C3 | TemplateCoach 兜底；离线准备 3~5 段预生成建议 |
| 公开视频带口令片段不够 | B6/B7 | 扩大关键词（中英文）；团队自拍补充 |
| 奖励动作纯视觉不可靠 | B8 | 默认用户打点，视觉仅可选增强 |
| 无同犬连续多日数据 | C3 | 同频道按时间排；不足用模拟数据并明确标注 |
| 大模型给出不安全建议 | C4 | 规则层定数字、安全层硬拦截 |
| 数据许可与署名 | D4 | 只用公开许可来源，`sources.csv` 记录，演示署名 |

---

## 8. 进度速览（工时汇总）

| 阶段 | 步骤 | 合计工时 | 结束时手上要有 |
|---|---|---|---|
| A 骨架与跑通 | A1～A9 | 12～16h | **一条命令跑通全链路**，`results/sample.json` 字段齐全 |
| B 换真实现 | B1～B8 | 14～20h | 真姿态/真口令/真奖励，`reports/B*.md` 基线齐全 |
| C 判定+处方+安全 | C1～C5 | 8～12h | 置信度门控、规则、Claude 建议、安全转介、30 用例报告 |
| D 演示与准备 | D1～D4 | 6～9h | 网页上传演示 + 彩排通过 |
| **合计** | | **40～55h** | 比赛当天有可演示结果 |

> 多人协作：A 阶段必须串行（一个人跑通即可）；B 阶段 B1～B4（姿态）与 B5～B7（口令）可两人并行；C、D 阶段可再分工。工时可叠加换算成日历天数。

---

## 附：与既有 CodePlan.md 的关键差异

| 维度 | 既有 CodePlan.md | 本计划（详细版 · 跑通优先 · 按工时） |
|---|---|---|
| 首要目标 | 分阶段验证假设（准确率是门槛） | **跑通链路**（准确率是记录项，不是门槛） |
| 验收 | 准确率阈值（如 hold 误差 ≤1s ≥80%） | **一条命令 + 可见产出 + 字段齐全** |
| 起步方式 | P0 收集标注 → P1 姿态（先做难的） | **A 阶段先用 stub 跑通端到端**，再逐项换真 |
| 接口与替换 | 未显式定义 | **Protocol 先行，stub→真实现不改编排** |
| 进度划分 | 按「天 / 周」 | **按工时（⏱），可碎片化推进** |
| 准确率目标 | 作为通过标准卡在每阶段 | 移到 §4「调准路线」，跑通后按优先级做 |
| 数据飞轮 | 未单列 | 单列 §5，A9 就落库 |
| 可管理性 | 阶段式描述 | 每步五步工作法 + 报告模板 + DoD + 工时记录 |
