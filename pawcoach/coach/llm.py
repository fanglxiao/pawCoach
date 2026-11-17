"""LLM 教练：调 OpenAI 兼容大模型 API 生成建议；无 key / 超时则兜底到 TemplateCoach。

后端是黑客松额度赞助商提供的 OpenAI 兼容地址（默认 https://api.openai-next.com/v1/chat/completions）。
base_url / model 可用 LLM_BASE_URL / LLM_MODEL 环境变量覆盖，key 从 LLM_API_KEY 读。
C3：prompt 注入本次指标 + 历史趋势 + 规则层输出 + SOP。
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

DEFAULT_BASE_URL = "https://api.openai-next.com/v1/chat/completions"
# 默认模型名（OpenAI 兼容）。赞助商支持哪些模型待确认，先用 gpt-4o-mini，
# 确认后用 LLM_MODEL 环境变量或构造参数覆盖，不用改代码。
DEFAULT_MODEL = "gpt-4o-mini"


class LLMCoach:
    def __init__(self, model: str | None = None, base_url: str | None = None):
        self.model = model or os.environ.get("LLM_MODEL", DEFAULT_MODEL)
        self.base_url = base_url or os.environ.get("LLM_BASE_URL", DEFAULT_BASE_URL)
        self._fallback = TemplateCoach()

    def plan(self, result: AnalysisResult, history: list[AnalysisResult]) -> str:
        api_key = os.environ.get("LLM_API_KEY")
        if not api_key:
            return self._fallback.plan(result, history)

        plan = plan_progress(result, history, target_hold=effective_target_hold(result))
        sop = retrieve_sop(sop_query_terms(plan), top_k=2)

        try:
            resp = httpx.post(
                self.base_url,
                headers={
                    "Authorization": f"Bearer {api_key}",
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
            data = resp.json()
            text = (data.get("choices", [{}])[0].get("message", {}) or {}).get("content", "")
            return (text or "").strip() or self._fallback.plan(result, history)
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
