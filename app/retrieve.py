"""混合检索：BM25 与哈希向量两路召回，RRF 融合后再按词面重合重排。"""

import math
import re
from collections import Counter

RRF_K = 60
DIM = 128


def tokens(text: str) -> list[str]:
    chars = re.findall(r"[\u4e00-\u9fff]", text)
    words = re.findall(r"[a-z0-9]+", text.lower())
    bigrams = [chars[i] + chars[i + 1] for i in range(len(chars) - 1)]
    return chars + bigrams + words


def _bm25(docs: list[list[str]], query: list[str]) -> list[float]:
    n = len(docs)
    avg = sum(len(doc) for doc in docs) / n if n else 1
    df: Counter[str] = Counter()
    for doc in docs:
        df.update(set(doc))
    scores = []
    for doc in docs:
        tf = Counter(doc)
        score = 0.0
        for term in query:
            if term not in tf:
                continue
            idf = math.log(1 + (n - df[term] + 0.5) / (df[term] + 0.5))
            freq = tf[term]
            score += idf * (freq * 2.2) / (freq + 1.2 * (0.25 + 0.75 * len(doc) / avg))
        scores.append(score)
    return scores


def _hash_vec(toks: list[str]) -> list[float]:
    vec = [0.0] * DIM
    for tok in toks:
        vec[hash(tok) % DIM] += 1.0
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def _cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def hybrid_search(docs: list[dict], query: str, limit: int = 3) -> list[dict]:
    if not docs or not query.strip():
        return []
    corpus = [tokens(f"{doc['title']} {doc['body']}") for doc in docs]
    q = tokens(query)
    if not q:
        return []
    bm25 = _bm25(corpus, q)
    qv = _hash_vec(q)
    dense = [_cosine(qv, _hash_vec(doc)) for doc in corpus]
    bm25_rank = _ranks(bm25)
    dense_rank = _ranks(dense)
    fused = []
    qset = set(q)
    for i, doc in enumerate(docs):
        overlap = len(qset & set(corpus[i])) / len(qset)
        rrf = 1 / (RRF_K + bm25_rank[i]) + 1 / (RRF_K + dense_rank[i])
        fused.append(
            {
                "id": doc["id"],
                "title": doc["title"],
                "body": doc["body"],
                "bm25": round(bm25[i], 4),
                "dense": round(dense[i], 4),
                "rrf": round(rrf, 6),
                "rerank": round(overlap, 4),
                "kind": doc.get("kind", ""),
            }
        )
    fused.sort(key=lambda row: (row["rerank"], row["rrf"]), reverse=True)
    return fused[:limit]


def _ranks(scores: list[float]) -> list[int]:
    order = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
    ranks = [0] * len(scores)
    for rank, idx in enumerate(order, start=1):
        ranks[idx] = rank
    return ranks
