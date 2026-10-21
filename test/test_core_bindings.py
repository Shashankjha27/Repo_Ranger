import repo_ranger_py as rrc


def test_merkle_bindings():
    t1 = rrc.PyMerkleTree()
    t1.add_file("f1.txt", b"abc")
    t1.add_file("f2.txt", b"def")

    t2 = rrc.PyMerkleTree()
    t2.add_file("f1.txt", b"abc")
    t2.add_file("f3.txt", b"ghi")

    diff = t1.diff(t2)
    assert diff.added == ["f3.txt"]
    assert diff.removed == ["f2.txt"]
    assert diff.modified == []


def test_ast_compression_and_symbols():
    code = b"pub fn compute_hash(val: &[u8]) -> u64 { 42 }"
    compressed = rrc.compress_ast("hash.rs", code)
    assert "{ ... }" in compressed

    symbols = rrc.extract_symbols("hash.rs", code)
    assert len(symbols) == 1
    assert symbols[0].name == "compute_hash"
    assert symbols[0].kind == "Function"


def test_database_and_search():
    db = rrc.PyCodeDatabase()
    code = "fn authenticate(user: str) -> bool { true }"
    db.index([("auth.rs", code)])

    hits = db.search("authenticate", 5)
    assert len(hits) == 1
    assert hits[0].file_path == "auth.rs"
    assert "<b>authenticate</b>" in hits[0].snippet

    syms = db.find_symbol("authenticate")
    assert len(syms) == 1
    assert syms[0].name == "authenticate"


def test_graph_and_pagerank():
    files = [
        ("caller.rs", "fn entrypoint() { helper(); }"),
        ("callee.rs", "fn helper() { let x = 1; }"),
    ]
    graph = rrc.PySymbolGraph.build(files)
    assert graph.get_callers("helper") == ["entrypoint"]
    assert graph.get_callees("entrypoint") == ["helper"]

    top = graph.top_symbols(1)
    assert len(top) == 1
    assert top[0][0] == "helper"
