"""LD-336: compare retrieval methods on the labelled benchmark in dataset.py.

Methods (same index chunks and same per-file query for all):
  tfidf      the production ranker (app.retrieval, TF-IDF cosine, threshold 0.05)
  embedding  average GloVe word vectors (100 d, Wikipedia + Gigaword), cosine similarity
  hybrid     0.5 x TF-IDF + 0.5 x embedding cosine
  (other rankers can be registered in RANKERS, e.g. by LD-337)

Metrics, separately for related code (k = 4) and documentation passages (k = 3), averaged
over the files that have at least one relevant item:
  Recall@k, Precision@k, MRR (rank of the first relevant hit), nDCG@k;
plus Noise = irrelevant items returned per file, over ALL files (also those with nothing
relevant, where every returned item is noise).

Run from ai-service/:
    python -m experiments.retrieval.benchmark            # downloads GloVe once (~130 MB)
    python -m experiments.retrieval.benchmark --no-embedding
    python -m experiments.retrieval.benchmark --glove /path/glove-wiki-gigaword-100.gz
"""
import argparse
import gzip
import math
import os
import pathlib
import time
import urllib.request
from collections import Counter
from typing import Callable, Dict, List, Optional, Tuple

from app.models import GenerateRequest
from app.normalize import normalize
from app.retrieval import MIN_SCORE, Chunk, RetrievalIndex, build_index, file_query, tokenize

from .dataset import GOLD, request

GLOVE_URL = ("https://github.com/RaRe-Technologies/gensim-data/releases/download/"
             "glove-wiki-gigaword-100/glove-wiki-gigaword-100.gz")
CACHE = pathlib.Path(os.getenv("LIVINGDOCS_CACHE", pathlib.Path.home() / ".cache" / "livingdocs"))
K = {"code": 4, "doc": 3}

Ranked = List[Tuple[float, Chunk]]
# A ranker gets the index, the query terms and the kind; it returns (score, chunk) for every
# candidate, best first. The threshold below which nothing is returned is per method.
Ranker = Callable[[RetrievalIndex, Counter, str, str], Ranked]


def key(c: Chunk) -> str:
    return f"{c.path}::{c.name}"


# ---------------- rankers ----------------

def tfidf_rank(index: RetrievalIndex, q: Counter, kind: str, exclude: str) -> Ranked:
    qw = index._weights(q)
    qn = math.sqrt(sum(w * w for w in qw.values())) or 1.0
    out = []
    for c, cn in zip(index.chunks, index._norms):
        if c.kind != kind or (kind == "code" and c.path == exclude):
            continue
        cw = index._weights(c.tokens)
        out.append((sum(qw[t] * cw[t] for t in qw.keys() & cw.keys()) / (qn * cn), c))
    out.sort(key=lambda x: (-x[0], x[1].path, x[1].name))
    return out


class Glove:
    def __init__(self, path: pathlib.Path, vocabulary: set) -> None:
        self.vectors: Dict[str, List[float]] = {}
        with gzip.open(path, "rt", encoding="utf-8") as fh:
            first = fh.readline().split()
            if len(first) > 2:                      # file without a header line
                fh.seek(0)
            for line in fh:
                word, rest = line.split(" ", 1)
                if word in vocabulary:
                    self.vectors[word] = [float(x) for x in rest.split()]

    def embed(self, tokens: Counter) -> Optional[List[float]]:
        vecs = [(self.vectors[t], n) for t, n in tokens.items() if t in self.vectors]
        if not vecs:
            return None
        dim = len(vecs[0][0])
        total = sum(n for _, n in vecs)
        v = [sum(vec[i] * n for vec, n in vecs) / total for i in range(dim)]
        norm = math.sqrt(sum(x * x for x in v)) or 1.0
        return [x / norm for x in v]


def embedding_ranker(glove: Glove) -> Ranker:
    cache: Dict[int, Optional[List[float]]] = {}

    def rank(index: RetrievalIndex, q: Counter, kind: str, exclude: str) -> Ranked:
        qv = glove.embed(q)
        out = []
        for c in index.chunks:
            if c.kind != kind or (kind == "code" and c.path == exclude):
                continue
            if id(c) not in cache:
                cache[id(c)] = glove.embed(c.tokens)
            cv = cache[id(c)]
            score = sum(a * b for a, b in zip(qv, cv)) if qv and cv else 0.0
            out.append((score, c))
        out.sort(key=lambda x: (-x[0], x[1].path, x[1].name))
        return out
    return rank


def hybrid_ranker(emb: Ranker, weight: float = 0.5) -> Ranker:
    def rank(index: RetrievalIndex, q: Counter, kind: str, exclude: str) -> Ranked:
        lex = {id(c): s for s, c in tfidf_rank(index, q, kind, exclude)}
        out = [(weight * lex.get(id(c), 0.0) + (1 - weight) * s, c) for s, c in emb(index, q, kind, exclude)]
        out.sort(key=lambda x: (-x[0], x[1].path, x[1].name))
        return out
    return rank


# ---------------- evaluation ----------------

def evaluate(index: RetrievalIndex, files, rank: Ranker, threshold: float) -> Dict[str, Dict[str, float]]:
    res = {}
    for kind, label in (("code", "code"), ("doc", "docs")):
        k = K[kind]
        rec, prec, mrr, ndcg, noise, n_eval = 0.0, 0.0, 0.0, 0.0, 0, 0
        for f in files:
            gold = set(GOLD[f.path][label])
            hits = [c for s, c in rank(index, file_query(f), kind, f.path) if s >= threshold][:k]
            got = [key(c) for c in hits]
            noise += sum(1 for g in got if g not in gold)
            if not gold:
                continue
            n_eval += 1
            rel = [1 if g in gold else 0 for g in got]
            rec += sum(rel) / min(len(gold), k)
            prec += sum(rel) / k
            mrr += next((1 / (i + 1) for i, r in enumerate(rel) if r), 0.0)
            dcg = sum(r / math.log2(i + 2) for i, r in enumerate(rel))
            ideal = sum(1 / math.log2(i + 2) for i in range(min(len(gold), k)))
            ndcg += dcg / ideal
        n = max(n_eval, 1)
        res[label] = {"recall": rec / n, "precision": prec / n, "mrr": mrr / n, "ndcg": ndcg / n,
                      "noise": noise / len(files)}
    return res


def per_file(index, files, rank: Ranker, threshold: float, label: str) -> Dict[str, List[str]]:
    kind = "code" if label == "code" else "doc"
    return {f.path: [key(c) for s, c in rank(index, file_query(f), kind, f.path) if s >= threshold][:K[kind]]
            for f in files}


def load_corpus():
    req = GenerateRequest.model_validate(request())
    for f in req.files:
        normalize(f)
    index = build_index(req)
    names = {key(c) for c in index.chunks}
    missing = sorted({g for v in GOLD.values() for lst in v.values() for g in lst} - names)
    assert not missing, f"gold labels without an index item: {missing}"
    return index, [f for f in req.files if f.status.value == "ok"]


def glove_path(arg: Optional[str]) -> pathlib.Path:
    if arg:
        return pathlib.Path(arg)
    path = CACHE / "glove-wiki-gigaword-100.gz"
    if not path.exists():
        CACHE.mkdir(parents=True, exist_ok=True)
        print(f"Downloading GloVe vectors to {path} ...")
        urllib.request.urlretrieve(GLOVE_URL, path)
    return path


def table(rows: List[Tuple[str, Dict[str, Dict[str, float]], float]]) -> str:
    head = ("| Method | Code R@4 | Code P@4 | Code MRR | Code nDCG@4 | Code noise | "
            "Docs R@3 | Docs P@3 | Docs MRR | Docs nDCG@3 | Docs noise | ms/file |")
    out = [head, "|" + "---|" * 12]
    for name, r, ms in rows:
        c, d = r["code"], r["docs"]
        out.append(f"| {name} | {c['recall']:.2f} | {c['precision']:.2f} | {c['mrr']:.2f} | {c['ndcg']:.2f} | "
                   f"{c['noise']:.2f} | {d['recall']:.2f} | {d['precision']:.2f} | {d['mrr']:.2f} | "
                   f"{d['ndcg']:.2f} | {d['noise']:.2f} | {ms:.2f} |")
    return "\n".join(out)


def timed(index, files, rank, thr):
    t = time.perf_counter()
    r = evaluate(index, files, rank, thr)
    return r, (time.perf_counter() - t) * 1000 / len(files)


RANKERS: Dict[str, Tuple[Ranker, float]] = {"tfidf": (tfidf_rank, MIN_SCORE)}
THRESHOLDS = [round(0.05 * i, 2) for i in range(0, 19)]


def tune(index, files, rank: Ranker) -> float:
    """Threshold with the best mean nDCG (code + docs); ties go to the higher threshold (less
    noise). Tuned on the same labels it is evaluated on, so tuned rows are optimistic."""
    best = max(THRESHOLDS, key=lambda t: (round(sum(r["ndcg"] for r in evaluate(index, files, rank, t).values()), 4), t))
    return best


def main(argv=None) -> str:
    ap = argparse.ArgumentParser()
    ap.add_argument("--glove")
    ap.add_argument("--no-embedding", action="store_true")
    ap.add_argument("--emb-threshold", type=float, default=0.80)
    ap.add_argument("--hybrid-threshold", type=float, default=0.45)
    ap.add_argument("--tune", action="store_true", help="also report each method at its best threshold")
    args = ap.parse_args(argv)

    index, files = load_corpus()
    methods = [(name, rank, thr) for name, (rank, thr) in RANKERS.items()]
    if not args.no_embedding:
        vocab = set(index.idf)
        t = time.perf_counter()
        glove = Glove(glove_path(args.glove), vocab)
        load_s = time.perf_counter() - t
        coverage = len(glove.vectors) / max(len(vocab), 1)
        emb = embedding_ranker(glove)
        methods.append(("embedding (GloVe-100)", emb, args.emb_threshold))
        methods.append(("hybrid (0.5 TF-IDF + 0.5 GloVe)", hybrid_ranker(emb), args.hybrid_threshold))
        print(f"GloVe: {coverage:.0%} of the {len(vocab)} index terms have a vector; loading took {load_s:.1f} s")
    rows = []
    for name, rank, thr in methods:
        rows.append((f"{name}, threshold {thr:g}", *timed(index, files, rank, thr)))
        if args.tune:
            best = tune(index, files, rank)
            if best != thr:
                rows.append((f"{name}, tuned threshold {best:g}", *timed(index, files, rank, best)))
    text = table(rows)
    print(text)
    return text


if __name__ == "__main__":
    main()
