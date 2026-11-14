"""LD-337: knowledge retrieval improvements (and a regression guard on the benchmark)."""
from app.models import ContextDocument, GenerateRequest
from app.retrieval import (CALL_BONUS, Links, build_index, code_names, common_path_terms, fold,
                           retrieve, singular, split_document, tokenize)
from experiments.retrieval import benchmark as b


def req(files, context=()):
    return GenerateRequest.model_validate({"scope": "repository", "target": "shop", "files": files,
                                           "context": [c.model_dump() for c in context]})


# ---------- tokens ----------

def test_vietnamese_diacritics_are_folded_so_prose_matches_identifiers():
    assert fold("Hóa Đơn") == "hoa don"
    assert tokenize("Hóa đơn gửi xe") == tokenize("HoaDonGuiXe") == ["hoa", "don", "gui", "xe"]
    assert tokenize("lượt_gửi") == ["luot", "gui"]
    assert tokenize("các hóa đơn của khách") == ["hoa", "don", "khach"]     # folded stop words


def test_plurals_are_folded():
    assert [singular(w) for w in ["products", "categories", "codes", "status", "class", "basis"]] == \
        ["product", "category", "code", "status", "class", "basis"]
    assert tokenize("getCartTotal cart_id") == ["get", "cart", "total", "cart", "id"]


def test_code_names_in_prose():
    assert code_names("Totals are computed by CartService using cart_id, not by the cart.") == \
        {"CartService", "cart_id"}


# ---------- index ----------

def test_terms_common_to_most_paths_are_not_used_in_queries():
    assert common_path_terms(["shop/a.py", "shop/b.py", "shop/c/d.py"]) == {"shop"}
    assert common_path_terms(["src/main/java/com/acme/A.java", "src/main/java/com/acme/B.java",
                              "src/main/java/com/acme/x/C.java", "tools/run.py"]) == \
        {"src", "main", "java", "com", "acme"}
    assert common_path_terms(["shop/a.py", "shop/b.py"]) == set()          # too few files to tell


def test_heading_only_passages_are_not_indexed():
    doc = ContextDocument(path="d.md", content="# Pricing\n\n## VAT\n\nPrices include VAT.\n")
    chunks = split_document(doc)
    assert [(c.name, c.section) for c in chunks] == [("VAT", "Pricing > VAT")]


def test_generic_intro_no_longer_wins_every_file():
    intro = ContextDocument(path="README.md", title="Shop",
                            content="# Shop\n\nOnline shop backend.\n\n## Vouchers\n\nVoucher codes give a discount.\n")
    files = [{"path": "shop/pricing/voucher.py", "functions": [{"name": "validate_voucher",
                                                               "parameters": [{"name": "code", "type": "str"}]}]},
             {"path": "shop/a.py", "functions": [{"name": "a"}]},
             {"path": "shop/b.py", "functions": [{"name": "b"}]}]
    r = req(files, [intro])
    docs = retrieve(build_index(r), r.files[0]).docs
    assert [d.name for d in docs] == ["Vouchers"]


# ---------- bonuses ----------

SERVICE = {"path": "app/billing.py", "classes": [{"name": "Ledger", "methods": [{"name": "post"}, {"name": "close"}]}]}
CALLER = {"path": "app/jobs.py", "functions": [{"name": "nightly", "source": "def nightly():\n    Ledger().close()"}]}
OTHER = {"path": "app/misc.py", "functions": [{"name": "close_ledger_window", "docstring": "close ledger window"}]}


def test_code_the_file_calls_gets_a_bonus():
    r = req([SERVICE, CALLER, OTHER])
    got = retrieve(build_index(r), r.files[1]).code                   # jobs.py calls Ledger().close()
    assert [c.name for c in got[:2]] == ["Ledger.close", "Ledger"]
    assert got[0].score > got[-1].score


def test_code_that_calls_the_file_gets_a_bonus():
    r = req([SERVICE, CALLER, OTHER])
    got = retrieve(build_index(r), r.files[0]).code                   # billing.py is called by jobs.py
    assert got[0].name == "nightly"


def test_passage_naming_a_class_of_the_file_gets_a_bonus():
    doc = ContextDocument(path="ops.md", content="# Ops\n\n## Closing\n\nAt midnight Ledger closes the day.\n\n"
                                                 "## Window\n\nThe close window is shown.\n")
    r = req([SERVICE, CALLER, OTHER], [doc])
    got = retrieve(build_index(r), r.files[0]).docs
    assert got[0].name == "Closing"


def test_scores_are_capped_at_one():
    index = build_index(req([SERVICE, CALLER, OTHER]))
    q = {"ledger": 3, "close": 3}
    from collections import Counter
    hits = index.search(Counter(q), "code", "app/jobs.py", 5, Links(uses={"Ledger", "close"}, defines={"nightly"}))
    assert all(0 < h.score <= 1.0 for h in hits) and CALL_BONUS > 0


# ---------- benchmark regression guard (numbers from Docs/Linh/LD-337) ----------

def test_benchmark_does_not_regress():
    index, files = b.load_corpus()
    base = b.evaluate(index, files, b.tfidf_rank, b.MIN_SCORE)
    prod = b.evaluate(index, files, b.production_ranker(), b.MIN_SCORE)
    assert prod["code"]["recall"] >= 0.95 and prod["code"]["ndcg"] >= 0.95
    assert prod["docs"]["mrr"] >= 0.90 and prod["docs"]["ndcg"] >= 0.70
    assert prod["docs"]["noise"] <= 1.0
    assert prod["docs"]["ndcg"] > base["docs"]["ndcg"] and prod["code"]["ndcg"] >= base["code"]["ndcg"]
