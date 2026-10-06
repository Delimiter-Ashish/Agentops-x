"""Questions with known answers, so every run gets an objective task_success label."""
import random
import re

from demo.tools import COMPANIES, FX_FROM_USD, PRICES_USD

NAMES = {v: k.title() for k, v in COMPANIES.items()}


def make_tasks(n, seed=0):
    rng = random.Random(seed)
    tasks = []
    for _ in range(n):
        cur = rng.choice([c for c in FX_FROM_USD if c != "USD"])
        if rng.random() < 0.5:
            t = rng.choice(list(PRICES_USD))
            q = f"What is the current price of one {NAMES[t]} share in {cur}?"
            expected = PRICES_USD[t] * FX_FROM_USD[cur]
        else:
            t1, t2 = rng.sample(list(PRICES_USD), 2)
            n1, n2 = rng.randint(2, 40), rng.randint(2, 40)
            q = f"I own {n1} shares of {NAMES[t1]} and {n2} shares of {NAMES[t2]}. What is my portfolio worth in {cur}?"
            expected = (n1 * PRICES_USD[t1] + n2 * PRICES_USD[t2]) * FX_FROM_USD[cur]
        tasks.append({"question": q, "expected": round(expected, 2), "currency": cur})
    return tasks


_NUM = r"-?\d[\d,]*\.?\d*"


def extract_answer(text):
    text = text if isinstance(text, str) else str(text or "")
    m = re.search(r"FINAL:\s*[^\d-]*(" + _NUM + ")", text or "")
    if m:
        return float(m.group(1).replace(",", ""))
    nums = re.findall(_NUM, text or "")
    return float(nums[-1].replace(",", "")) if nums else None


def check(answer_text, expected, rel_tol=0.005):
    got = extract_answer(answer_text)
    return got is not None and abs(got - expected) <= rel_tol * abs(expected), got
