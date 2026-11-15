"""LD-336: the retrieval benchmark (labels, metrics, rankers) works without downloading anything."""
import gzip

from experiments.retrieval import benchmark as b
from experiments.retrieval.dataset import GOLD


def test_every_label_points_at_an_index_item_and_every_file_is_labelled():
    index, files = b.load_corpus()            # asserts that no label is missing from the index
    assert {f.path for f in files} == set(GOLD)
    assert index.stats().files == 14 and index.stats().documents == 5


def test_tfidf_metrics_are_in_range_and_reproducible():
    index, files = b.load_corpus()
    first = b.evaluate(index, files, b.tfidf_rank, b.MIN_SCORE)
    second = b.evaluate(index, files, b.tfidf_rank, b.MIN_SCORE)
    assert first == second
    for part in first.values():
        for name in ("recall", "precision", "mrr", "ndcg"):
            assert 0.0 <= part[name] <= 1.0
    assert first["code"]["recall"] >= 0.85          # LD-336 baseline: 0.91


def test_benchmark_ranker_matches_production_retrieval():
    from app.retrieval import retrieve
    index, files = b.load_corpus()
    f = files[1]
    prod = [b.key(c) for c in retrieve(index, f).code]
    bench = [b.key(c) for s, c in b.production_ranker()(index, f, "code") if s >= b.MIN_SCORE][:4]
    assert prod == bench


def test_embedding_and_hybrid_rankers_with_tiny_vectors(tmp_path):
    vec = tmp_path / "tiny.gz"
    with gzip.open(vec, "wt", encoding="utf-8") as fh:
        fh.write("3 2\ncart 1 0\nbasket 0.9 0.1\npassword 0 1\n")
    glove = b.Glove(vec, {"cart", "basket", "password", "missing"})
    assert set(glove.vectors) == {"cart", "basket", "password"}
    from collections import Counter
    v = glove.embed(Counter({"cart": 1}))
    assert abs(sum(x * x for x in v) - 1) < 1e-9
    assert glove.embed(Counter({"missing": 1})) is None
    index, files = b.load_corpus()
    emb = b.embedding_ranker(glove)
    for rank in (emb, b.hybrid_ranker(emb)):
        out = b.evaluate(index, files, rank, 0.0)
        assert set(out) == {"code", "docs"}


def test_command_line_without_embedding():
    text = b.main(["--no-embedding"])
    assert text.splitlines()[2].startswith("| tfidf, threshold 0.05 |")
