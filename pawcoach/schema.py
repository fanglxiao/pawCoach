"""PawCoach 统一数据结构（全链路合约）。

这是「视频 → JSON → 教练建议」整条链路唯一的合约：
所有模块都往这套结构里填，所有验收都检查这套结构是否字段齐全、类型正确。

约定（见 docs/CodePlan_DS.md §1.2）：
- 本模块 A 阶段就定死，后续只增字段、不破坏既有字段。
- 大模型只读这些「数字」，绝不直接看视频（K9-Bench 依据）。
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Literal, Optional

# 狗姿态标签：sit 坐 / stand 站 / down 卧 / unclear 看不清
PoseLabel = Literal["sit", "stand", "down", "unclear"]

# 音频事件类型：cue 口令 / marker 标记词 / release 释放词 / other 其它
AudioKind = Literal["cue", "marker", "release", "other"]

# 奖励事件来源：tap 用户打点 / marker 标记词 / visual 视觉
RewardSource = Literal["tap", "marker", "visual"]

# 一轮结束原因：release 释放 / stand_up 自行起身 / unknown 未知
EndedBy = Literal["release", "stand_up", "unknown"]


@dataclass
class MetaInfo:
    """用户录视频/上传时填写的元信息（对应 data/raw/<id>.meta.json）。"""

    cues: list[str] = field(default_factory=list)          # 训练口令词，如 ["坐"]
    marker_words: list[str] = field(default_factory=list)  # 标记词，如 ["好", "对"]
    release_words: list[str] = field(default_factory=list) # 释放词，如 ["可以了", "走"]
    reward_taps: list[float] = field(default_factory=list) # 手动打点的奖励时刻（秒）


@dataclass
class PoseSegment:
    """一段狗姿态时间区间。"""

    t_start: float
    t_end: float
    label: PoseLabel
    conf: float  # 0~1，越低越不可信


@dataclass
class AudioEvent:
    """一个命中的口令/标记词/释放词事件。"""

    word: str  # 命中的词（坐/好/可以了/sit/…）
    t_start: float
    t_end: float
    kind: AudioKind


@dataclass
class RewardEvent:
    """一个奖励事件时刻。"""

    t: float
    source: RewardSource


@dataclass
class Trial:
    """一轮训练：一次 cue → 进入坐姿 → 保持 → 结束/奖励。"""

    cue_t: Optional[float] = None          # 口令时刻
    sit_start: Optional[float] = None      # 进入坐姿时刻
    sit_end: Optional[float] = None        # 离开坐姿时刻
    ended_by: Optional[EndedBy] = None
    reward_t: Optional[float] = None       # 奖励时刻
    latency: Optional[float] = None        # 反应延迟 = sit_start - cue_t
    hold: Optional[float] = None           # 保持时长 = sit_end - sit_start
    reward_delay: Optional[float] = None   # 奖励延迟
    conf: float = 0.0                      # 本轮整体置信度


@dataclass
class Quality:
    """整段视频的可测量质量，用于置信度门控。"""

    dog_visible_ratio: float = 0.0
    audio_ok: bool = False
    pose_conf_mean: float = 0.0


@dataclass
class Summary:
    """聚合指标。"""

    trials: int = 0
    success_rate: Optional[float] = None
    median_hold: Optional[float] = None


@dataclass
class AnalysisResult:
    """一次 analyze 的最终结果，写入 results/<video_id>.json。"""

    video_id: str = ""
    dog_id: str = ""
    date: str = ""
    quality: Quality = field(default_factory=Quality)
    trials: list[Trial] = field(default_factory=list)
    summary: Summary = field(default_factory=Summary)
    unpaired: list[dict] = field(default_factory=list)  # 无法配对的事件，作反馈素材
    coach: str = ""                                     # 教练建议文本


def to_json(result: AnalysisResult) -> str:
    """把结果序列化为带缩进、非 ASCII 的 JSON 字符串。"""
    return json.dumps(asdict(result), ensure_ascii=False, indent=2)
