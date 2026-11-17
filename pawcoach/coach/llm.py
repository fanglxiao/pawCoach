"""LLM 教练：调大模型 API 生成建议；无 key / 超时则兜底到 TemplateCoach。

命名不绑定具体厂商（Claude/OpenAI/…），当前后端是 Anthropic Messages API，
换后端只改这里的请求实现。C3：prompt 注入本次指标 + 历史趋势 + 规则层输出 + SOP。
原则：大模型只读结构化数字，不看视频（K9-Bench 依据）。
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict

import httpx

from pawcoach.coach.rules import effective_target_hold, plan_progress, sop_query_terms
from pawcoach.coach.sop import retrieve_sop
from pawcoach.coach.template import TemplateCoach
from pawcoach.schema import AnalysisResult, to_json


class LLMCoach:
    # 默认模型 claude-sonnet-5-5（当前 Anthropic 后端），可传 model 换其它模型
    def __init__(self, model: str = "claude-sonnet-5-5"):
        self.model = model
        self._fallback = TemplateCoach()

    def plan(self, result: AnalysisResult, history: list[AnalysisResult]) -> str:
        api_key = os.environ.get("LLM_API_KEY")
        if not api_key:
            return self._fallback.plan(result, history)

        plan = plan_progress(result, history, target_hold=effective_target_hold(result))
        sop = retrieve_sop(sop_query_terms(plan), top_k=2)

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
                    "max_tokens": 600,
                    "messages": [
                        {"role": "user", "content": self._build_prompt(result, history, plan, sop)}
                    ],
                },
                timeout=30.0,
            )
            resp.raise_for_status()
            text = "".join(b.get("text", "") for b in resp.json().get("content", []))
            return text.strip() or self._fallback.plan(result, history)
        except Exception:
            return self._fallback.plan(result, history)

    @staticmethod
    def _build_prompt(
        result: AnalysisResult, history: list[AnalysisResult], plan, sop: str
    ) -> str:
        history_json = (
            json.dumps([asdict(r) for r in history[-3:]], ensure_ascii=False)
            if history
            else "（无历史）"
        )
        return (
            "你是一位正向强化训犬教练。基于以下结构化指标（不要看视频），"
            "用中文给出三点，每一点都要引用具体视频时间点（秒）：\n"
            "1. 做得好的一点；\n2. 最需改的一点；\n3. 下次怎么练。\n"
            f"规则层建议：下次目标保持 {plan.target_hold:.1f} 秒，"
            f"本次重点「{plan.focus or '无'}」。{plan.session}\n"
            f"SOP 参考：\n{sop or '（无相关 SOP）'}\n"
            f"历史趋势（最近 3 次）：\n{history_json}\n"
            f"本次指标：\n{to_json(result)}"
        )
