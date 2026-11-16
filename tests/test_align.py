"""align 的对齐逻辑单元测试（pytest 风格，也可 `python -m pytest tests/` 运行）。"""

from pawcoach.events.align import align
from pawcoach.schema import AudioEvent, MetaInfo, PoseSegment, RewardEvent


def test_single_trial_alignment():
    pose = [PoseSegment(t_start=3.0, t_end=9.0, label="sit", conf=0.9)]
    audio = [
        AudioEvent(word="坐", t_start=2.0, t_end=2.3, kind="cue"),
        AudioEvent(word="好", t_start=8.5, t_end=8.7, kind="marker"),
        AudioEvent(word="可以了", t_start=9.0, t_end=9.2, kind="release"),
    ]
    rewards = [RewardEvent(t=9.2, source="tap")]
    meta = MetaInfo(cues=["坐"], marker_words=["好"], release_words=["可以了"])

    trials, unpaired = align(pose, audio, rewards, meta)

    assert len(trials) == 1
    t = trials[0]
    assert t.cue_t == 2.0
    assert t.sit_start == 3.0
    assert t.sit_end == 9.0
    assert t.ended_by == "release"
    assert t.reward_t == 9.2
    assert t.latency == 1.0
    assert t.hold == 6.0
    assert t.reward_delay == 0.7  # 9.2 - 8.5（标记词）
    assert unpaired == []


def test_cue_without_sit_is_unpaired():
    pose: list[PoseSegment] = []
    audio = [AudioEvent(word="坐", t_start=2.0, t_end=2.3, kind="cue")]
    meta = MetaInfo(cues=["坐"])

    trials, unpaired = align(pose, audio, [], meta)

    assert trials == []
    assert len(unpaired) == 1
    assert unpaired[0]["type"] == "cue_without_sit"
