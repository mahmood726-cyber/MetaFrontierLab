import json
from pathlib import Path, PurePath


def test_submission_config_is_repo_relative():
    config_path = Path(__file__).parent.parent / "e156-submission" / "config.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))

    assert config["title"].startswith("MetaFrontierLab:")
    assert config["type"] == "methods"
    assert not PurePath(config["path"]).is_absolute()
    assert config["path"] == ".."


def test_readme_run_commands_are_repo_local():
    readme = (Path(__file__).parent.parent / "README.md").read_text(encoding="utf-8")

    assert "C:\\MetaFrontierLab" not in readme
    assert "/mnt/c/MetaFrontierLab" not in readme
    assert "python run_demo.py" in readme
    assert "python run_benchmarks.py --replications 4" in readme
