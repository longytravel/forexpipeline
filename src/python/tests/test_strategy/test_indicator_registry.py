"""Tests for indicator type registry (AC #2, #5)."""

import pytest

from strategy.indicator_registry import (
    IndicatorMeta,
    get_indicator_params,
    get_registry,
    is_indicator_known,
    reset_registry,
)


@pytest.fixture(autouse=True)
def _clear_registry():
    reset_registry()
    yield
    reset_registry()


def test_known_indicators_include_d10_minimum():
    """SMA, EMA, ATR, BollingerBands, RSI, MACD all known."""
    d10_minimum = ["sma", "ema", "atr", "bollinger_bands", "rsi", "macd"]
    for ind in d10_minimum:
        assert is_indicator_known(ind), f"{ind} should be known"


def test_all_24_indicators_loaded():
    """All 24 indicators loaded (20 original + hidden_smash_day + market_structure + swing_pullback + channel_breakout)."""
    registry = get_registry()
    # 24 indicators: 4 trend + 6 volatility + 6 momentum + 3 price_action + 5 structure
    assert len(registry) == 24


def test_unknown_indicator_returns_false():
    """Random string -> False."""
    assert is_indicator_known("magic_oscillator_9000") is False
    assert is_indicator_known("") is False
    assert is_indicator_known("SMA") is False  # Case-sensitive: "sma" not "SMA"


def test_indicator_meta_has_required_params():
    """SMA has 'period', ATR has 'period', MACD has fast/slow/signal."""
    sma = get_indicator_params("sma")
    assert "period" in sma.required_params

    atr = get_indicator_params("atr")
    assert "period" in atr.required_params

    macd = get_indicator_params("macd")
    assert "fast_period" in macd.required_params
    assert "slow_period" in macd.required_params
    assert "signal_period" in macd.required_params


def test_indicator_meta_categories():
    """Indicators have correct categories."""
    assert get_indicator_params("sma").category == "trend"
    assert get_indicator_params("atr").category == "volatility"
    assert get_indicator_params("rsi").category == "momentum"
    assert get_indicator_params("rolling_max").category == "structure"


def test_get_unknown_indicator_raises_keyerror():
    """Unknown indicator -> KeyError."""
    with pytest.raises(KeyError, match="Unknown indicator"):
        get_indicator_params("nonexistent")


def test_indicator_meta_is_pydantic_model():
    """IndicatorMeta instances are proper Pydantic models."""
    meta = get_indicator_params("ema")
    assert isinstance(meta, IndicatorMeta)
    assert meta.name == "EMA"
    assert meta.description != ""


def test_registry_extensible_from_toml(tmp_path):
    """Registry loads from custom TOML path (extensible without code changes)."""
    custom_toml = tmp_path / "custom_registry.toml"
    custom_toml.write_text(
        '[indicators.custom_ind]\n'
        'name = "Custom"\n'
        'category = "trend"\n'
        'description = "A custom indicator"\n'
        'required_params = ["period"]\n'
        'optional_params = []\n',
        encoding="utf-8",
    )

    assert is_indicator_known("custom_ind", registry_path=custom_toml)
    assert not is_indicator_known("sma", registry_path=custom_toml)
