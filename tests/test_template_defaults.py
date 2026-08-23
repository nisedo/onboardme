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
