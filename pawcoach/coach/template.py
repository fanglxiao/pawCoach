"""模板教练：确定性的建议文本，保证跑通、无外部依赖。

阶段 C 由 ClaudeCoach + 规则层 + 安全层替换/增强。
"""

from __future__ import annotations

from pawcoach.schema import AnalysisResult


class TemplateCoach:
    def plan(self, result: AnalysisResult, history: list[AnalysisResult]) -> str:
        n = result.summary.trials
        reliable = result.summary.reliable_trials
        med = result.summary.median_hold
        lines = [
            "【PawCoach 教练建议（模板版）】",
            f"本次识别到 {n} 轮训练。",
        ]
        if reliable and reliable != n:
            lines.append(f"其中 {reliable} 轮可靠，{n - reliable} 轮置信度不足、未计入指标。")
        if med is not None:
            lines.append(f"保持时长中位数约 {med:.1f} 秒。")
        if result.quality.unclear_seconds > 0:
            lines.append(f"本段有 {result.quality.unclear_seconds:.1f} 秒无法可靠判断，未计入上述指标。")
        lines.append("（此为阶段 A 模板输出，Claude 处方在阶段 C 接入。）")
        return "\n".join(lines)
