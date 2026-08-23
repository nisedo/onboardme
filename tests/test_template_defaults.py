import re
from pathlib import Path


def test_code_font_default_is_readable_and_consistent():
    template = (
        Path(__file__).resolve().parent.parent / "template.html"
    ).read_text(encoding="utf-8")

    css_size = int(
        re.search(r"--code-font-size:\s*(\d+)px", template).group(1)
    )
    css_line_height = int(
        re.search(r"--code-line-height:\s*(\d+)px", template).group(1)
    )
    js_default = int(
        re.search(r"const CODE_FONT_DEFAULT = (\d+);", template).group(1)
    )

    assert css_size == js_default == 14
    assert css_line_height == round(css_size * 1.4)


def test_cards_do_not_render_segmented_top_edge_ornament():
    template = (
        Path(__file__).resolve().parent.parent / "template.html"
    ).read_text(encoding="utf-8")

    assert 'class="absolute top-0 right-0 flex gap-1"' not in template


def test_function_headers_prioritize_centered_contract_and_signature():
    template = (
        Path(__file__).resolve().parent.parent / "template.html"
    ).read_text(encoding="utf-8")

    assert "const safeName = node.name" not in template
    assert 'class="node-header-title w-full min-w-0 px-24 font-mono text-base' in template
    assert "${node.contractName}.sol" in template
    assert "${node.signature.split('.', 2)[1] || node.signature}" in template
