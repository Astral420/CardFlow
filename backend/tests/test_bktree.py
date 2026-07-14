from app.dedup.bktree import BKTree


def _hamming(a: str, b: str) -> int:
    return bin(int(a, 16) ^ int(b, 16)).count("1")


def test_bktree_finds_close_matches():
    tree: BKTree[str] = BKTree(_hamming)
    tree.add("f0f0f0f0f0f0f0f0", "a")
    tree.add("f0f0f0f0f0f0f0f1", "b")  # 1 bit away from a
    tree.add("0000000000000000", "c")  # far away

    results = tree.query("f0f0f0f0f0f0f0f0", max_distance=2)
    payloads = {payload for payload, _dist in results}
    assert payloads == {"a", "b"}


def test_bktree_respects_distance_bound():
    tree: BKTree[str] = BKTree(_hamming)
    tree.add("ffffffffffffffff", "a")
    tree.add("0000000000000000", "b")

    results = tree.query("ffffffffffffffff", max_distance=0)
    assert [payload for payload, _ in results] == ["a"]


def test_bktree_handles_duplicate_values():
    tree: BKTree[str] = BKTree(_hamming)
    tree.add("aaaaaaaaaaaaaaaa", "first")
    tree.add("aaaaaaaaaaaaaaaa", "second")

    results = tree.query("aaaaaaaaaaaaaaaa", max_distance=0)
    payloads = {payload for payload, _ in results}
    assert payloads == {"first", "second"}
