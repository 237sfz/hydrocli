from __future__ import annotations

import json

from hydro_cli.parsing import (
    choose_markdown,
    extract_ui_context,
    extract_user_context,
    rewrite_attachment_links,
)


def encode_context(data: dict[str, object]) -> str:
    payload = json.dumps(data, ensure_ascii=False)
    escaped = payload.encode("unicode_escape").decode("ascii").replace("'", "\\'")
    return f"<script>window.UiContextNew = '{escaped}';</script>"


def test_extract_ui_context_handles_escaped_quote_and_unicode() -> None:
    html = encode_context({"pdoc": {"title": "引号 ' 和中文", "content": {"zh": "正文"}}})

    data = extract_ui_context(html)

    assert data["pdoc"]["title"] == "引号 ' 和中文"


def test_extract_user_context() -> None:
    payload = json.dumps({"_id": 3, "uname": "237sfz"}, ensure_ascii=False)
    escaped = payload.encode("unicode_escape").decode("ascii")
    html = f"<script>window.UserContext = '{escaped}';</script>"

    data = extract_user_context(html)

    assert data["_id"] == 3
    assert data["uname"] == "237sfz"


def test_choose_markdown_prefers_chinese_then_english() -> None:
    assert choose_markdown({"zh": "中文", "en": "English"}) == "中文"
    assert choose_markdown({"zh": "", "en": "English"}) == "English"
    assert choose_markdown("plain") == "plain"


def test_rewrite_attachment_links() -> None:
    markdown = (
        "[a](file://data.zip)\n"
        "[b](/p/18/file/data.zip?type=additional_file)\n"
        "[c](http://localhost:8888/p/18/file/other.zip?type=additional_file)\n"
    )

    rewritten = rewrite_attachment_links(
        markdown,
        "http://localhost:8888",
        "18",
        {"data.zip"},
    )

    assert "[a](files/data.zip)" in rewritten
    assert "[b](files/data.zip)" in rewritten
    assert "other.zip" in rewritten
