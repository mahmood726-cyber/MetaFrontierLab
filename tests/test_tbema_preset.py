from __future__ import annotations

import pytest

from metafrontier import (
    SimulationConfig,
    make_tbema_analyzer,
    simulate_publication_biased_binary_meta,
)
from metafrontier.benchmark_methods import _tbema_payload
from metafrontier.simulation import (
    moderator_columns,
    profile_columns,
    target_moderators_for_config,
)


def test_tbema_payload_matches_canonical_preset() -> None:
    config = SimulationConfig(seed=7, studies=18, moderator_count=2)
    observed, _ = simulate_publication_biased_binary_meta(config)

    analyzer = make_tbema_analyzer()
    result = analyzer.fit(
        observed,
        moderator_cols=moderator_columns(config.moderator_count),
        profile_cols=profile_columns(),
        target_profile=list(config.target_profile),
        target_moderators=target_moderators_for_config(config).tolist(),
        design_strength_col="design_strength",
    )
    payload = _tbema_payload(observed, config)

    assert payload["estimate"] == pytest.approx(result.estimate)
    assert payload["std_error"] == pytest.approx(result.std_error)
    assert payload["ci_low"] == pytest.approx(result.ci_low)
    assert payload["ci_high"] == pytest.approx(result.ci_high)
    assert payload["tau"] == pytest.approx(result.tau)
