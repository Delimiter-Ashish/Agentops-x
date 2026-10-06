"""Offline scripted 'LLM' for tests and demos without an API key.

It follows the tool-use protocol like a real model (lookup -> price -> fx -> calculator -> answer)
and makes realistic mistakes: occasionally a wrong company name or a final answer computed by hand.
"""
import random
import re
import uuid

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult


class FakeFinanceLLM(BaseChatModel):
    model_name: str = "fake-finance-llm"

    @property
    def _llm_type(self):
        return "fake-finance"

    def bind_tools(self, tools, **kw):
        return self

    @property
    def _identifying_params(self):
        return {"model": self.model_name}

    def _call(self, name, **args):
        return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": f"call_{uuid.uuid4().hex[:8]}"}])

    def _generate(self, messages, stop=None, run_manager=None, **kw):
        system = messages[0].content if messages else ""
        q = next(m.content for m in messages if isinstance(m, HumanMessage))
        results = [m.content for m in messages if isinstance(m, ToolMessage)]
        good = [r for r in results if not r.startswith("ERROR")]
        holdings = re.findall(r"(\d+) shares of (\w+)", q) or [("1", re.search(r"one (\w+) share", q).group(1))]
        cur = q.rstrip("?").split()[-1]
        rng = random.Random(hash((q, len(messages))))
        step = len(good)
        n_h = len(holdings)
        if step < n_h:  # lookups
            name = holdings[step][1]
            if results and results[-1].startswith("ERROR") or rng.random() > 0.1:
                msg = self._call("lookup_ticker", company=name)
            else:
                msg = self._call("lookup_ticker", company=name + "Corp")  # model mistake -> tool error
        elif step < 2 * n_h:
            msg = self._call("get_stock_price", ticker=good[step - n_h])
        elif step == 2 * n_h:
            msg = self._call("get_fx_rate", base="USD", quote=cur)
        elif step == 2 * n_h + 1 and ("calculator" in system or rng.random() < 0.6):
            prices, fx = good[n_h:2 * n_h], good[2 * n_h]
            expr = " + ".join(f"{h[0]} * {p}" for h, p in zip(holdings, prices))
            msg = self._call("calculator", expression=f"({expr}) * {fx}")
        else:
            if step == 2 * n_h + 2:
                value = float(good[-1])
            else:  # "mental math" with rounded numbers: often wrong
                value = sum(int(h[0]) * round(float(p)) for h, p in zip(holdings, good[n_h:2 * n_h])) * round(float(good[2 * n_h]), 1)
            msg = AIMessage(content=f"FINAL: {value:.2f}" if "FINAL" in system else f"It is about {value:,.2f} {cur}.")
        n_in = sum(len(str(m.content)) for m in messages) // 4
        msg.usage_metadata = {"input_tokens": n_in, "output_tokens": 30, "total_tokens": n_in + 30}
        return ChatResult(generations=[ChatGeneration(message=msg)])
