from __future__ import annotations

import metafrontier.benchmark_methods as benchmark_methods


def test_external_method_availability_is_probed_independently(monkeypatch) -> None:
    availability = {
        ("metafor",): (True, "Rscript"),
        ("meta", "metasens"): (False, "missing metasens"),
        ("RoBMA",): (False, "missing RoBMA"),
    }

    monkeypatch.setattr(benchmark_methods, "_r_package_environment", lambda packages: availability[packages])

    methods = benchmark_methods.available_benchmark_methods(include_external=True)

    assert "metafor_trimfill_external" in methods
    assert "metafor_selmodel_external" in methods
    assert "copas_selection_external" not in methods
    assert "robma_bibma_external" not in methods
