from git_hunk._skills import _parse_frontmatter


def test_inline_scalars() -> None:
    meta = _parse_frontmatter("---\nname: foo\nlicense: MIT\n---\nbody\n")
    assert meta == {"name": "foo", "license": "MIT"}


def test_long_inline_description_is_kept_verbatim() -> None:
    meta = _parse_frontmatter("---\ndescription: one. two. Use when x.\n---\n")
    assert meta["description"] == "one. two. Use when x."


def test_only_top_level_keys_are_parsed() -> None:
    text = "---\nname: foo\nmetadata:\n  author: bar\nallowed-tools:\n  - Bash\n---\n"
    meta = _parse_frontmatter(text)
    assert meta == {"name": "foo", "metadata": "", "allowed-tools": ""}


def test_missing_frontmatter_returns_empty() -> None:
    assert _parse_frontmatter("# just markdown\n") == {}


def test_missing_closing_delimiter_returns_empty() -> None:
    # Without a terminating ---, the body must not be absorbed as metadata.
    text = "---\nname: core\nfoo: from_body\n\n# Heading\n"
    assert _parse_frontmatter(text) == {}
