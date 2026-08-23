from pathlib import Path

import main as flow_gen


class _Contract:
    def __init__(self, name: str):
        self.name = name


def test_generate_from_local_writes_index_linking_every_dashboard(
    tmp_path, monkeypatch
):
    project = tmp_path / "sample-project"
    project.mkdir()
    (project / "Contracts.sol").write_text(
        "contract Alpha {} contract Beta {}", encoding="utf-8"
    )
    output_dir = tmp_path / "site"
    contracts = [_Contract("Beta"), _Contract("Alpha")]

    monkeypatch.setattr(flow_gen, "Slither", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(
        flow_gen, "_select_local_root_contracts", lambda _slither: contracts
    )
    monkeypatch.setattr(
        flow_gen,
        "build_entry_point_flows",
        lambda _slither, selected, progress_cb=None: [
            {"entry_point": f"{selected[0].name}.run()"}
        ],
    )
    monkeypatch.setattr(
        flow_gen,
        "build_read_only_entry_point_flows",
        lambda _slither, _selected, progress_cb=None: [],
    )
    monkeypatch.setattr(
        flow_gen,
        "_collect_render_metadata",
        lambda _slither, _selected: {
            "extra_storage_vars": [],
            "type_aliases": [],
            "libraries": [],
            "events": [],
            "interfaces": [],
        },
    )
    monkeypatch.setattr(
        flow_gen,
        "_solidity_label_for_main_contract",
        lambda _slither, _contract: "Solidity",
    )

    def fake_render_html(
        _views,
        _default_contract,
        chain,
        address,
        _title,
        _solidity_label,
        output_dir=None,
        progress_cb=None,
    ):
        del progress_cb
        output_path = Path(output_dir) / f"{chain}_{address}.html"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text("dashboard", encoding="utf-8")
        return output_path

    monkeypatch.setattr(flow_gen, "render_html", fake_render_html)

    results = flow_gen.generate_from_local(project, output_dir=output_dir)

    assert len(results) == 2
    index_path = results[0]["index_path"]
    assert index_path == results[1]["index_path"]
    assert index_path.parent == output_dir
    assert index_path.name.startswith("local_")
    assert index_path.name.endswith("_index.html")

    page = index_path.read_text(encoding="utf-8")
    assert page.index("Alpha") < page.index("Beta")
    for result in results:
        assert result["output_path"].name in page
        assert result["contract"] in page
    assert "2 deployable root contracts" in page


def test_local_index_escapes_project_and_contract_names(tmp_path):
    output_dir = tmp_path / "site"
    project = tmp_path / "project<&>"
    result_path = output_dir / 'local_hash_Name.html'
    results = [
        {
            "output_path": result_path,
            "contract": "Name<script>",
            "entry_count": 1,
        }
    ]

    index_path = flow_gen._render_local_project_index(
        project, "hash", results, output_dir=output_dir
    )
    page = index_path.read_text(encoding="utf-8")

    assert "Name&lt;script&gt;" in page
    assert "project&lt;&amp;&gt;" in page
    assert "Name<script>" not in page
