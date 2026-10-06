"""Tools for the demo finance agent: deterministic data + configurable infrastructure faults.

Faults (env vars, per call):
  DEMO_TIMEOUT_RATE  probability a market-data call raises TimeoutError (retried by LangGraph)
  DEMO_SLOW_RATE     probability a call stalls for ~1.5 s (latency spikes)
Bad inputs (unknown company, bad expression) return "ERROR: ..." so the agent can recover.
"""
import ast
import operator
import os
import random
import time

from langchain_core.tools import tool

COMPANIES = {"apple": "AAPL", "microsoft": "MSFT", "nvidia": "NVDA", "tesla": "TSLA",
             "amazon": "AMZN", "alphabet": "GOOGL", "meta": "META", "netflix": "NFLX"}
PRICES_USD = {"AAPL": 227.52, "MSFT": 415.26, "NVDA": 131.38, "TSLA": 248.90,
              "AMZN": 186.34, "GOOGL": 165.81, "META": 573.10, "NFLX": 701.45}
FX_FROM_USD = {"USD": 1.0, "EUR": 0.9213, "GBP": 0.7794, "JPY": 149.52, "INR": 83.91, "CAD": 1.3612}


def _faults():
    if random.random() < float(os.environ.get("DEMO_SLOW_RATE", 0.10)):
        time.sleep(1.5)
    if random.random() < float(os.environ.get("DEMO_TIMEOUT_RATE", 0.15)):
        raise TimeoutError("market data service timed out")


@tool
def lookup_ticker(company: str) -> str:
    """Return the stock ticker symbol for a company name, e.g. 'Apple' -> 'AAPL'."""
    t = COMPANIES.get(company.strip().lower())
    return t if t else f"ERROR: unknown company '{company}'. Known: {', '.join(c.title() for c in COMPANIES)}"


@tool
def get_stock_price(ticker: str) -> str:
    """Return the latest price in USD for a stock ticker symbol like 'AAPL'."""
    _faults()
    price = PRICES_USD.get(ticker.strip().upper())
    return f"{price:.2f}" if price else f"ERROR: unknown ticker '{ticker}'. Use lookup_ticker first."


@tool
def get_fx_rate(base: str, quote: str) -> str:
    """Return how many units of `quote` currency one unit of `base` currency buys, e.g. USD->EUR."""
    _faults()
    b, q = base.strip().upper(), quote.strip().upper()
    if b not in FX_FROM_USD or q not in FX_FROM_USD:
        return f"ERROR: unsupported currency. Supported: {', '.join(FX_FROM_USD)}"
    return f"{FX_FROM_USD[q] / FX_FROM_USD[b]:.6f}"


_OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
        ast.USub: operator.neg, ast.Pow: operator.pow}


def _eval(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_eval(node.left), _eval(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_eval(node.operand))
    raise ValueError("unsupported expression")


@tool
def calculator(expression: str) -> str:
    """Evaluate an arithmetic expression with + - * / ** and parentheses, e.g. '12 * 227.52 * 0.92'."""
    try:
        return f"{_eval(ast.parse(expression, mode='eval').body):.6f}"
    except (ValueError, SyntaxError, ZeroDivisionError, TypeError) as e:
        return f"ERROR: could not evaluate '{expression}': {e}"


TOOLS = [lookup_ticker, get_stock_price, get_fx_rate, calculator]
