# PawCoach（AI 宠物训练教练）

基于手机训练视频的宠物行为训练 Agent —— 测量「口令 → 动作 → 奖励」的时间关系，积累训练记录，并生成下一次练习建议。

> 当前阶段：**Hackathon MVP**。只做「坐下 + 等待保持（Sit-Stay）」一个场景，只用公开 / 可授权数据。

## 一句话

把「视频 → JSON → 教练建议」这条链路跑通：先测量可回溯的数字（保持时长、反应延迟、奖励延迟……），再由规则 + 大模型「读数字」生成建议——**不让大模型直接看视频下结论**（依据 K9-Bench 实测，见 [datasets-and-papers.md §1](docs/datasets-and-papers.md)）。

## 文档

- **[MVP 开发计划（跑通优先 · 按工时）](docs/CodePlan_detail.md)** ← 执行入口
- [开发进度](docs/PROGRESS.md)（当前：阶段 A 完成，阶段 B 做完 B1～B5，下一步 B6）
- [CodePlan（风险优先版）](docs/CodePlan.md)
- [数据集与论文调研](docs/datasets-and-papers.md)（最全，含许可红线与实测核对）
- [技术资源精选](docs/pet-training-agent-technical-resources.md)
- [早期调研](docs/research.md)

## 快速开始（计划完成后）

```bash
# 1. 环境
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt        # 阶段 A 轻装；阶段 B 再装模型依赖

# 2. 查看视频信息
python -m pawcoach.cli probe data/raw/<video_id>.mp4

# 3. 分析一段训练视频
python -m pawcoach.cli analyze data/raw/<video_id>.mp4 -o results/<video_id>.json
```

输入：`data/raw/<video_id>.mp4` + 可选 `data/raw/<video_id>.meta.json`（口令词、手动打点的奖励时刻）。
输出：`results/<video_id>.json`（结构化指标）+ 一段可读的教练建议。

## 技术栈

Python 3.11 · ffmpeg · SuperAnimal / mmpose · Ultralytics YOLO · FunASR / Whisper · MediaPipe · FastAPI · SQLite · Claude API

## 数据与许可

仅使用公开 / 可授权数据；来源与许可记录在 `data/sources.csv`，演示与文档满足 CC BY 署名要求。许可红线（哪些能商用、哪些仅研究用途）见 [datasets-and-papers.md §4.2](docs/datasets-and-papers.md)。

## 目录结构

见 [CodePlan_detail.md §6](docs/CodePlan_detail.md) 的完整规划。
