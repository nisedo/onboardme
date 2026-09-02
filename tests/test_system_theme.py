from pathlib import Path

import main as flow_gen


ROOT = Path(__file__).resolve().parent.parent


def _assert_system_theme_detector(document: str) -> None:
    assert "window.matchMedia('(prefers-color-scheme: dark)')" in document
    assert "document.documentElement.dataset.theme = theme;" in document
    assert "systemTheme.addEventListener('change', applySystemTheme);" in document
    assert "systemTheme.addListener(applySystemTheme);" in document
    assert 'html[data-theme="light"]' in document


def test_static_pages_follow_system_theme_and_update_live():
    for path in (ROOT / "src" / "index.html", ROOT / "template.html"):
        document = path.read_text(encoding="utf-8")
        _assert_system_theme_detector(document)

        detector_position = document.index("window.matchMedia")
        body_position = document.index("<body")
        assert detector_position < body_position


def test_local_project_index_follows_system_theme_and_updates_live(tmp_path):
    project = tmp_path / "sample-project"
    project.mkdir()
    dashboard = tmp_path / "site" / "local_hash_Example.html"

    index_path = flow_gen._render_local_project_index(
        project,
        "hash",
        [
            {
                "output_path": dashboard,
                "contract": "Example",
                "entry_count": 1,
            }
        ],
        output_dir=dashboard.parent,
    )

    document = index_path.read_text(encoding="utf-8")
    _assert_system_theme_detector(document)
    assert "--theme-bg: #f8fafc;" in document
    assert "background: var(--theme-bg)" in document
