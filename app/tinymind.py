"""字符级单层语言模型，用来演示词表、交叉熵和损失下降。

权重是「上一个字 → 下一个字」的打分矩阵，几百步 SGD 就能在商城文案上过拟合。
这不是 64M 预训练模型，只保留面试要讲的训练回路。
"""

import json
import math
import random
from pathlib import Path

from app.database import DATA_DIR

WEIGHTS = DATA_DIR / "tinymind.json"


def train(text: str, steps: int = 400, lr: float = 0.5) -> dict:
    chars = sorted(set(text))
    if len(chars) < 2 or len(text) < 2:
        raise ValueError("语料太短")
    index = {ch: i for i, ch in enumerate(chars)}
    n = len(chars)
    weight = [[0.0] * n for _ in range(n)]
    pairs = [(text[i], text[i + 1]) for i in range(len(text) - 1)]
    rng = random.Random(7)
    losses = []
    for _ in range(steps):
        prev, nxt = rng.choice(pairs)
        row = index[prev]
        target = index[nxt]
        loss, probs = _softmax_loss(weight[row], target)
        for k in range(n):
            weight[row][k] -= lr * (probs[k] - (1.0 if k == target else 0.0))
        losses.append(loss)
    payload = {
        "chars": chars,
        "weight": weight,
        "steps": steps,
        "loss_start": round(sum(losses[:20]) / 20, 4),
        "loss_end": round(sum(losses[-20:]) / 20, 4),
        "vocab": n,
        "corpus_chars": len(text),
    }
    WEIGHTS.write_text(json.dumps(payload), encoding="utf-8")
    return {key: payload[key] for key in ("steps", "loss_start", "loss_end", "vocab", "corpus_chars")}


def status() -> dict:
    if not WEIGHTS.exists():
        return {"trained": False}
    data = _load()
    return {
        "trained": True,
        "steps": data["steps"],
        "loss_start": data["loss_start"],
        "loss_end": data["loss_end"],
        "vocab": data["vocab"],
        "corpus_chars": data["corpus_chars"],
    }


def generate(prompt: str, n: int = 40) -> str:
    data = _load()
    chars = data["chars"]
    index = {ch: i for i, ch in enumerate(chars)}
    weight = data["weight"]
    if not prompt:
        prompt = chars[0]
    current = prompt[-1] if prompt[-1] in index else chars[0]
    out = [prompt]
    rng = random.Random(len(prompt) + n)
    for _ in range(max(1, min(n, 80))):
        row = weight[index[current]]
        current = _sample(chars, row, rng)
        out.append(current)
    return "".join(out)


def _load() -> dict:
    if not WEIGHTS.exists():
        raise FileNotFoundError("还没有训练")
    return json.loads(WEIGHTS.read_text(encoding="utf-8"))


def _softmax_loss(logits: list[float], target: int) -> tuple[float, list[float]]:
    peak = max(logits)
    exps = [math.exp(x - peak) for x in logits]
    total = sum(exps) or 1.0
    probs = [item / total for item in exps]
    return -math.log(probs[target] + 1e-12), probs


def _sample(chars: list[str], logits: list[float], rng: random.Random) -> str:
    peak = max(logits)
    exps = [math.exp(x - peak) for x in logits]
    total = sum(exps) or 1.0
    pick = rng.random() * total
    acc = 0.0
    for ch, exp in zip(chars, exps):
        acc += exp
        if acc >= pick:
            return ch
    return chars[-1]


def corpus_path() -> Path:
    return WEIGHTS
