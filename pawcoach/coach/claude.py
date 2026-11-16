"""Claude 教练：调 Claude API 生成建议；无 key / 超时则兜底到 TemplateCoach。

原则：大模型只读结构化数字，不看视频（K9-Bench 依据）。
阶段 C 再注入规则层输出 + 历史趋势 + SOP 检索。
"""

from __future__ import annotations

import os

import httpx

from pawcoach.coach.template import TemplateCoach
from pawcoach.schema import AnalysisResult, to_json


class ClaudeCoach:
    def __init__(self, model: str = "claude-sonnet-5-5"):
        self.model = model
        self._fallback = TemplateCoach()

    def plan(self, result: AnalysisResult, history: list[AnalysisResult]) -> str:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            return self._fallback.plan(result, history)

        try:
            resp = httpx.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": self.model,
                    "max_tokens": 400,
                    "messages": [
                        {"role": "user", "content": self._build_prompt(result, history)}
                    ],
                },
                timeout=20.0,
            )
            resp.raise_for_status()
            text = "".join(b.get("text", "") for b in resp.json().get("content", []))
            return text.strip() or self._fallback.plan(result, history)
        except Exception:
            return self._fallback.plan(result, history)

    @staticmethod
    def _build_prompt(result: AnalysisResult, history: list[AnalysisResult]) -> str:
        return (
            "你是一位正向强化训犬教练。基于以下结构化指标（不要看视频），"
            "用中文给出：做得好的一点、最需改的一点、下次怎么练。\n"
            f"{to_json(result)}"
        )
