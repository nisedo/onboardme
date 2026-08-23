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

    assert css_size == js_default == 18
    assert css_line_height == round(css_size * 1.4)
    assert "const CODE_FONT_STORAGE_KEY = 'codeFontSizeV2';" in template
    assert "stored = rawStored === null ? null : Number(rawStored);" in template


def test_cards_do_not_render_segmented_top_edge_ornament():
    template = (
        Path(__file__).resolve().parent.parent / "template.html"
    ).read_text(encoding="utf-8")

    assert 'class="absolute top-0 right-0 flex gap-1"' not in template


def test_function_headers_vertically_center_contract_and_signature():
    template = (
        Path(__file__).resolve().parent.parent / "template.html"
    ).read_text(encoding="utf-8")

    assert "const safeName = node.name" not in template
    assert "flex items-center justify-between" in template
    assert 'class="flex items-center gap-4 min-w-0"' in template
    assert 'class="node-header-title min-w-0 font-mono text-xl' in template
    assert "node-header-title w-full" not in template
    assert "${node.contractName}.sol" in template
    assert "${node.signature.split('.', 2)[1] || node.signature}" in template


def test_dashboard_omits_footer_tagline():
    template = (
        Path(__file__).resolve().parent.parent / "template.html"
    ).read_text(encoding="utf-8")

    assert "May the bugs be with you" not in template
    assert 'class="h-6 bg-[#040812] border-t border-cyan-900/30' not in template
    assert 'class="flex space-x-1"' not in template


def test_local_dashboards_link_back_to_project_index():
    template = (
        Path(__file__).resolve().parent.parent / "template.html"
    ).read_text(encoding="utf-8")

    assert 'id="project-home"' in template
    assert 'href="local_${localProjectId}_index.html"' in template
    assert "(CONTRACT_CHAIN || '').toLowerCase() === 'local'" in template
