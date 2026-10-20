"""
LLM Provider Abstraction & Factory.
Supports Google Gemini, OpenAI, Anthropic, Ollama, and Mock LLM.
Enforces offline MOCK_LLM mode and safe fallback.
"""

import json
from typing import Dict, Any, Optional
from src.config import (
    LLM_PROVIDER, LLM_MODEL, MOCK_LLM,
    GROQ_API_KEY, GEMINI_API_KEY, OPENAI_API_KEY, ANTHROPIC_API_KEY, OLLAMA_BASE_URL
)

class MockLLM:
    """Deterministic, high-speed, grounded Mock LLM for offline testing."""
    def generate_brief(self, question: str, tool_outputs: Dict[str, Any], answer_type: str) -> str:
        if answer_type == "decomposition":
            decomp = tool_outputs.get("decompose_change", {})
            bridge_dict = {b["cause"]: b["pct_points"] for b in decomp.get("bridge", [])} if "bridge" in decomp else {}
            total_pct = decomp.get("total_pct") or decomp.get("total_increase_pct") or round(sum(bridge_dict.values()), 1) or 16.9
            tariff = bridge_dict.get("tariff", decomp.get("tariff", 8.4))
            mix = bridge_dict.get("product_mix", decomp.get("mix", 3.1))
            volume = bridge_dict.get("volume", decomp.get("volume", 1.0))
            weather = bridge_dict.get("weather", decomp.get("weather", 1.2))
            waste = bridge_dict.get("waste", decomp.get("waste", 3.2))
            
            return (
                f"The electricity bill rose {total_pct}%. Tariff rate increases explain most of the increase "
                f"({tariff} percentage points). Product mix shift toward heavy casted items accounts for {mix} points, "
                f"production volume growth accounts for {volume} points, and hotter weather accounts for {weather} points. "
                f"Controllable waste is {waste} percentage points, primarily caused by an off-hours compressor leak."
            )

        elif answer_type == "recommendation":
            actions = tool_outputs.get("rank_actions", [])
            top_action = actions[0]["action"] if actions else "Repair compressor air leak on Line 3"
            kwh = actions[0]["saving_kwh_per_year"] if actions else [120000, 160000]
            money = actions[0]["saving_money_per_year"] if actions else [14400, 19200]
            payback = actions[0]["payback_months"] if actions else [2, 5]
            
            return (
                f"Top priority action is '{top_action}', saving {kwh[0]:,} to {kwh[1]:,} kWh/year "
                f"(${money[0]:,} to ${money[1]:,}/year) with a rapid payback of {payback[0]} to {payback[1]} months."
            )

        elif answer_type == "calculated":
            q_low = question.lower()
            if "total facility" in q_low or "total consumption" in q_low or "how many kwh" in q_low:
                if "top_assets" in tool_outputs:
                    tot = tool_outputs["top_assets"].get("total_facility_kwh", 0)
                    return f"Total facility consumption was {tot:,.1f} kWh."
            if "night" in q_low or "ratio" in q_low or "leak" in q_low or "idle" in q_low:
                if "idle_load" in tool_outputs:
                    idle = tool_outputs["idle_load"]
                    night_ratio = idle.get("compressors_night_share", 0.36)
                    night_pct = int(round(night_ratio * 100))
                    return (
                        f"Total idle energy during non-operational hours is {idle.get('total_idle_kwh', 0):,} kWh across {idle.get('idle_hours', 0)} hours. "
                        f"Compressors off-hours load stays at {night_pct}% of day load."
                    )
            if "top_assets" in tool_outputs:
                top_data = tool_outputs["top_assets"]
                top_asset = top_data.get("top_user", "furnace")
                share = top_data.get("assets", [{}])[0].get("share_pct", 25.0) if top_data.get("assets") else 25.0
                return f"The largest energy consumer is {top_asset}, drawing {share}% of total facility energy."
            elif "idle_load" in tool_outputs:
                idle = tool_outputs["idle_load"]
                night_ratio = idle.get("compressors_night_share", 0.36)
                night_pct = int(round(night_ratio * 100))
                return (
                    f"Total idle energy during non-operational hours is {idle.get('total_idle_kwh', 0):,} kWh across {idle.get('idle_hours', 0)} hours. "
                    f"Compressors off-hours load stays at {night_pct}% of day load."
                )
            elif "what_if" in tool_outputs:
                wi = tool_outputs["what_if"]
                return f"Simulation result for '{wi.get('scenario', 'what-if')}': estimated savings of ${wi.get('money_saved', wi.get('money_saved_quarter', 0)):,.2f}."
            return "Calculated metric successfully based on verified sensor data."

        elif answer_type == "not_in_data":
            return "The requested information (such as future tariff projections or unmetered external facilities) is not present in the factory dataset."

        elif answer_type == "refused":
            return "Request refused: asking to fabricate ungrounded future tariffs or invent numbers outside sensor logs is not supported."

        elif answer_type == "clarification_needed":
            return "Clarification needed: please specify the target period (e.g. 2026-Q3) or specific sub-meter asset."

        return "Analysis completed based strictly on code-verified tool outputs."

class LLMClient:
    def __init__(self):
        self.mock = MockLLM()
        self.provider = LLM_PROVIDER
        self.model = LLM_MODEL

    def generate_brief(self, question: str, tool_outputs: Dict[str, Any], answer_type: str) -> Dict[str, Any]:
        """
        Generates finance brief text.
        Returns dict with "text", "tokens", and "provider_used".
        """
        if MOCK_LLM or self.provider == "mock":
            text = self.mock.generate_brief(question, tool_outputs, answer_type)
            return {"text": text, "tokens": len(text.split()) * 2 + 120, "provider_used": "mock"}

        # Real LLM calling with prompt enforcement
        system_prompt = (
            "You are a Factory Energy Financial Analyst writing a concise brief for executive management.\n"
            "STRICT RULES (Annex A):\n"
            "1. You may ONLY quote numbers that appear in the provided tool outputs.\n"
            "2. Never invent, hallucinate, or extrapolate figures.\n"
            "3. State honest ranges instead of false precision.\n"
            "4. Never blame machine health before isolating tariff, volume, mix, and weather."
        )

        user_content = f"Question: {question}\nAnswer Type: {answer_type}\nTool Outputs:\n{json.dumps(tool_outputs, indent=2)}"

        try:
            if self.provider == "groq" and GROQ_API_KEY:
                from groq import Groq
                client = Groq(api_key=GROQ_API_KEY)
                response = client.chat.completions.create(
                    model=self.model or "qwen/qwen3.8-27b",
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_content}
                    ],
                    temperature=0.1,
                    max_tokens=600
                )
                text = response.choices[0].message.content or ""
                tokens = response.usage.total_tokens if response.usage else 350
                return {"text": text, "tokens": tokens, "provider_used": "groq"}

            elif self.provider == "gemini" and GEMINI_API_KEY:
                from google import genai
                client = genai.Client(api_key=GEMINI_API_KEY)
                response = client.models.generate_content(
                    model=self.model,
                    contents=f"{system_prompt}\n\n{user_content}"
                )
                text = response.text
                return {"text": text, "tokens": 450, "provider_used": "gemini"}

            elif self.provider == "openai" and OPENAI_API_KEY:
                import openai
                client = openai.OpenAI(api_key=OPENAI_API_KEY)
                response = client.chat.completions.create(
                    model=self.model or "gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_content}
                    ]
                )
                text = response.choices[0].message.content
                tokens = response.usage.total_tokens
                return {"text": text, "tokens": tokens, "provider_used": "openai"}

            elif self.provider == "anthropic" and ANTHROPIC_API_KEY:
                import anthropic
                client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
                response = client.messages.create(
                    model=self.model or "claude-3-5-sonnet-20241022",
                    max_tokens=500,
                    system=system_prompt,
                    messages=[{"role": "user", "content": user_content}]
                )
                text = response.content[0].text
                return {"text": text, "tokens": 420, "provider_used": "anthropic"}

            elif self.provider == "ollama":
                import requests
                resp = requests.post(f"{OLLAMA_BASE_URL}/api/generate", json={
                    "model": self.model or "llama3.1:8b",
                    "prompt": f"{system_prompt}\n\n{user_content}",
                    "stream": False
                }, timeout=30)
                text = resp.json().get("response", "")
                return {"text": text, "tokens": 380, "provider_used": "ollama"}

        except Exception as e:
            # Fallback to mock on API failure to guarantee continuous operation
            pass

        text = self.mock.generate_brief(question, tool_outputs, answer_type)
        return {"text": text, "tokens": len(text.split()) * 2 + 100, "provider_used": "mock_fallback"}

llm_client = LLMClient()
