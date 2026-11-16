"""模板教练：确定性的建议文本，保证跑通、无外部依赖。

阶段 C 由 ClaudeCoach + 规则层 + 安全层替换/增强。
"""

from __future__ import annotations

from pawcoach.schema import AnalysisResult


class TemplateCoach:
    def plan(self, result: AnalysisResult, history: list[AnalysisResult]) -> str:
        n = result.summary.trials
        med = result.summary.median_hold
        lines = [
            "【PawCoach 教练建议（模板版）】",
            f"本次识别到 {n} 轮训练。",
        ]
        if med is not None:
            lines.append(f"保持时长中位数约 {med:.1f} 秒。")
        lines.append("（此为阶段 A 模板输出，Claude 处方在阶段 C 接入。）")
        return "\n".join(lines)
