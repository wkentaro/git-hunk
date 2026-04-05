from git_hunk._hunk import _split_hunk


def test_single_region_no_split() -> None:
    header = "@@ -1,5 +1,6 @@ def foo():"
    body = [" ctx1", " ctx2", "+added", " ctx3", " ctx4"]
    result = _split_hunk("f.py", header, body)
    assert len(result) == 1


def test_small_gap_no_split() -> None:
    """Gap of 5 context lines (< 2*3+1=7) — should NOT split."""
    header = "@@ -1,12 +1,14 @@ def foo():"
    body = [
        " ctx1",
        "+add1",
        " ctx2",
        " ctx3",
        " ctx4",
        " ctx5",
        " ctx6",
        "+add2",
        " ctx7",
    ]
    result = _split_hunk("f.py", header, body)
    assert len(result) == 1


def test_large_gap_splits() -> None:
    """Gap of 7 context lines (>= 2*3+1=7) — should split into 2."""
    header = "@@ -1,14 +1,16 @@ def foo():"
    body = [
        " ctx1",
        "+add1",
        " g1",
        " g2",
        " g3",
        " g4",
        " g5",
        " g6",
        " g7",
        "+add2",
        " ctx2",
    ]
    result = _split_hunk("f.py", header, body)
    assert len(result) == 2
    assert any(line.startswith("+") for line in result[0]["body_lines"])
    assert "+add1" in result[0]["body_lines"]
    assert "+add2" in result[1]["body_lines"]


def test_three_regions_two_gaps() -> None:
    header = "@@ -1,30 +1,33 @@ def foo():"
    body = [
        " ctx",
        "+add1",
        " g1",
        " g2",
        " g3",
        " g4",
        " g5",
        " g6",
        " g7",
        "+add2",
        " g8",
        " g9",
        " g10",
        " g11",
        " g12",
        " g13",
        " g14",
        "+add3",
        " ctx_end",
    ]
    result = _split_hunk("f.py", header, body)
    assert len(result) == 3


def test_preserves_context_around_changes() -> None:
    header = "@@ -1,16 +1,18 @@ def foo():"
    body = [
        " c1",
        " c2",
        "+add1",
        " g1",
        " g2",
        " g3",
        " g4",
        " g5",
        " g6",
        " g7",
        "+add2",
        " c3",
        " c4",
    ]
    result = _split_hunk("f.py", header, body)
    assert len(result) == 2
    first_body = result[0]["body_lines"]
    assert first_body[0] == " c1"
    assert "+add1" in first_body
    assert len([line for line in first_body if not line.startswith("+")]) <= 5


def test_header_line_numbers() -> None:
    header = "@@ -1,14 +1,16 @@ def foo():"
    body = [
        " ctx1",
        "+add1",
        " g1",
        " g2",
        " g3",
        " g4",
        " g5",
        " g6",
        " g7",
        "+add2",
        " ctx2",
    ]
    result = _split_hunk("f.py", header, body)
    assert len(result) == 2
    assert result[0]["header"].startswith("@@ -1,")
    assert "-6," in result[1]["header"] or "-5," in result[1]["header"]


def test_deletions() -> None:
    header = "@@ -1,14 +1,12 @@"
    body = [
        " ctx1",
        "-del1",
        " g1",
        " g2",
        " g3",
        " g4",
        " g5",
        " g6",
        " g7",
        "-del2",
        " ctx2",
    ]
    result = _split_hunk("f.py", header, body)
    assert len(result) == 2
    assert "-del1" in result[0]["body_lines"]
    assert "-del2" in result[1]["body_lines"]


def test_no_body_lines() -> None:
    header = "@@ -1,0 +1,0 @@"
    result = _split_hunk("f.py", header, [])
    assert len(result) == 1
