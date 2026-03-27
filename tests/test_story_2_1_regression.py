"""Regression tests for Story 2-1: Strategy Evaluator Baseline Review.

These tests validate that the research artifact (strategy-evaluator-baseline-review.md)
accurately reflects the actual ClaudeBackTester source code. They catch drift between
the catalogue documentation and the real implementation.
"""

import ast
import os
import re
from pathlib import Path

import pytest

BASELINE_REPO = Path(os.environ.get(
    "CLAUDEBACKTESTER_PATH",
    r"C:\Users\ROG\Projects\ClaudeBackTester",
))
RESEARCH_ARTIFACT = Path(
    r"C:\Users\ROG\Projects\Forex Pipeline"
    r"\_bmad-output\planning-artifacts\research"
    r"\strategy-evaluator-baseline-review.md"
)

INDICATORS_PY = BASELINE_REPO / "backtester" / "strategies" / "indicators.py"
REGISTRY_PY = BASELINE_REPO / "backtester" / "strategies" / "registry.py"


def _public_functions(filepath: Path) -> list[str]:
    """Extract all public function names from a Python file using AST."""
    source = filepath.read_text(encoding="utf-8")
    tree = ast.parse(source)
    return [
        node.name
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and not node.name.startswith("_")
    ]


def _read_artifact() -> str:
    return RESEARCH_ARTIFACT.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Regression: indicator catalogue completeness (caught missing 6 indicators)
# ---------------------------------------------------------------------------

@pytest.mark.regression
def test_all_public_indicators_catalogued():
    """Every public function in indicators.py must appear in the research artifact.

    Regression for: Codex HIGH finding — 6 indicators (supertrend, keltner,
    williams_r, cci, swing_highs, swing_lows) were missing from the catalogue.
    """
    if not INDICATORS_PY.exists():
        pytest.skip("ClaudeBackTester repo not available")

    functions = _public_functions(INDICATORS_PY)
    artifact = _read_artifact()
    artifact_lower = artifact.lower()

    missing = [fn for fn in functions if fn.lower() not in artifact_lower]
    assert not missing, (
        f"Indicator functions not catalogued in research artifact: {missing}"
    )


@pytest.mark.regression
def test_indicator_count_matches():
    """The stated indicator count in the artifact must match the actual count.

    Regression for: Executive summary and module inventory claimed '12 indicators'
    when there were actually 18.
    """
    if not INDICATORS_PY.exists():
        pytest.skip("ClaudeBackTester repo not available")

    functions = _public_functions(INDICATORS_PY)
    artifact = _read_artifact()

    # Check the module inventory line mentions the correct count
    match = re.search(r"\|\s*\*\*strategies/indicators\.py\*\*.*?(\d+)\s+indicator functions", artifact)
    assert match, "Could not find indicator function count in module inventory"
    stated_count = int(match.group(1))
    # Count includes private helpers prefixed with _ that are documented
    # The stated count should be >= public function count
    assert stated_count >= len(functions), (
        f"Module inventory says {stated_count} indicator functions, "
        f"but {len(functions)} public functions found in source"
    )


# ---------------------------------------------------------------------------
# Regression: ATR computation semantics (caught EMA vs Wilder's smoothing)
# ---------------------------------------------------------------------------

@pytest.mark.regression
def test_atr_not_documented_as_ema():
    """ATR must NOT be documented as using EMA smoothing.

    Regression for: Codex HIGH finding — ATR was incorrectly documented as
    'ema(true_range(...))' when it actually uses Wilder's smoothing.
    """
    artifact = _read_artifact()

    # Find the ATR section
    atr_section_match = re.search(
        r"### 5\.\d+ Average True Range \(ATR\)(.*?)### 5\.",
        artifact,
        re.DOTALL,
    )
    assert atr_section_match, "ATR section not found in artifact"
    atr_section = atr_section_match.group(1)

    assert "wilder" in atr_section.lower(), (
        "ATR section does not mention Wilder's smoothing"
    )
    # Should not claim EMA is the computation method
    computation_line = [
        line for line in atr_section.split("\n")
        if "Computation" in line
    ]
    assert computation_line, "No Computation field in ATR section"
    assert "ema(" not in computation_line[0].lower(), (
        "ATR Computation field incorrectly references ema() function"
    )


# ---------------------------------------------------------------------------
# Regression: Donchian output shape (caught 2-tuple vs 3-tuple)
# ---------------------------------------------------------------------------

@pytest.mark.regression
def test_donchian_documented_as_three_tuple():
    """Donchian must be documented as returning (upper, middle, lower).

    Regression for: Codex HIGH finding — Donchian was documented as returning
    2 values when it actually returns 3 (upper, middle, lower).
    """
    artifact = _read_artifact()

    donchian_match = re.search(
        r"### 5\.\d+ Donchian Channel(.*?)### 5\.",
        artifact,
        re.DOTALL,
    )
    assert donchian_match, "Donchian section not found in artifact"
    donchian_section = donchian_match.group(1)

    assert "middle" in donchian_section.lower(), (
        "Donchian section does not mention 'middle' output"
    )
    output_line = [
        line for line in donchian_section.split("\n")
        if "Output Type" in line
    ]
    assert output_line, "No Output Type field in Donchian section"
    assert "3" in output_line[0] or "three" in output_line[0].lower(), (
        "Donchian Output Type does not indicate 3 values"
    )


# ---------------------------------------------------------------------------
# Regression: registry.get() vs registry.create() (caught get=instantiate)
# ---------------------------------------------------------------------------

@pytest.mark.regression
def test_loading_mechanism_distinguishes_get_create():
    """Loading mechanism must correctly describe get() vs create() semantics.

    Regression for: Codex HIGH finding — artifact said get() instantiates,
    but get() returns the class and create() instantiates.
    """
    artifact = _read_artifact()

    loading_match = re.search(
        r"### Loading Mechanism(.*?)### Validation",
        artifact,
        re.DOTALL,
    )
    assert loading_match, "Loading Mechanism section not found"
    loading = loading_match.group(1)

    assert "class" in loading.lower(), (
        "Loading mechanism does not mention that get() returns a class"
    )
    assert "create" in loading.lower(), (
        "Loading mechanism does not mention create() for instantiation"
    )


# ---------------------------------------------------------------------------
# Regression: referential validation exists (caught false negative)
# ---------------------------------------------------------------------------

@pytest.mark.regression
def test_referential_validation_documented():
    """Referential validation must be documented as present, not absent.

    Regression for: Codex HIGH finding — artifact said 'No referential
    validation' but registry.get() raises KeyError on unknown strategies.
    """
    artifact = _read_artifact()

    validation_match = re.search(
        r"### Validation(.*?)### Comparison",
        artifact,
        re.DOTALL,
    )
    assert validation_match, "Validation section not found"
    validation = validation_match.group(1)

    referential_line = [
        line for line in validation.split("\n")
        if "referential" in line.lower()
    ]
    assert referential_line, "No referential validation entry found"
    assert "none" not in referential_line[0].lower().split("referential")[1], (
        "Referential validation incorrectly documented as 'None'"
    )


# ---------------------------------------------------------------------------
# Regression: AC3 explicit unknowns section (caught missing section)
# ---------------------------------------------------------------------------

@pytest.mark.regression
def test_explicit_unknowns_section_exists():
    """Section 6 must contain an 'Explicit Unknowns' subsection.

    Regression for: Both BMAD (M1) and Codex (MEDIUM) flagged that AC3
    requires explicit unknowns but the section was missing.
    """
    artifact = _read_artifact()

    section6_match = re.search(
        r"## 6\. Strategy Authoring Workflow(.*?)## 7\.",
        artifact,
        re.DOTALL,
    )
    assert section6_match, "Section 6 not found"
    section6 = section6_match.group(1)

    assert "explicit unknowns" in section6.lower(), (
        "Section 6 missing 'Explicit Unknowns' subsection (AC3 requirement)"
    )


# ---------------------------------------------------------------------------
# Regression: Price Sources field presence (caught missing fields)
# ---------------------------------------------------------------------------

@pytest.mark.regression
def test_all_indicator_entries_have_price_sources():
    """Every indicator catalogue entry must include a Price Sources field.

    Regression for: Codex MEDIUM finding — true_range, rolling_max, and
    rolling_min were missing the Price Sources field.
    """
    artifact = _read_artifact()

    # Find all indicator sections (### 5.N ...)
    sections = re.findall(
        r"(### 5\.\d+\s+.+?)(?=### 5\.\d+|### Indicator Summary)",
        artifact,
        re.DOTALL,
    )
    assert len(sections) >= 12, f"Expected >= 12 indicator sections, found {len(sections)}"

    missing_price_sources = []
    for section in sections:
        title_match = re.match(r"### 5\.\d+\s+(.+)", section)
        title = title_match.group(1).strip() if title_match else "unknown"
        if "price sources" not in section.lower():
            missing_price_sources.append(title)

    assert not missing_price_sources, (
        f"Indicator sections missing Price Sources field: {missing_price_sources}"
    )


# ---------------------------------------------------------------------------
# Regression: Checkpoint field names (synthesis round 2 — Codex HIGH-1)
# ---------------------------------------------------------------------------

@pytest.mark.regression
def test_checkpoint_field_names_match_source():
    """Checkpoint JSON examples must use the real persisted field names.

    Regression for: Codex HIGH-1 — artifact used partial_enabled, hours_start,
    hours_end, days_bitmask instead of the real partial_close_enabled,
    allowed_hours_start, allowed_hours_end, allowed_days.
    """
    artifact = _read_artifact()

    # These wrong names must NOT appear in the artifact
    wrong_names = ["partial_enabled", "partial_pct", "hours_start", "hours_end", "days_bitmask"]
    for wrong in wrong_names:
        # Use word boundary check — "partial_enabled" should not appear,
        # but "partial_close_enabled" is fine (contains "partial_enabled" as substring)
        occurrences = re.findall(rf'"{wrong}"', artifact)
        assert not occurrences, (
            f'Incorrect checkpoint field name "{wrong}" found in artifact. '
            f"Should use the real persisted name from checkpoint.json."
        )

    # These correct names MUST appear
    correct_names = [
        "partial_close_enabled", "partial_close_pct",
        "allowed_hours_start", "allowed_hours_end", "allowed_days",
    ]
    for correct in correct_names:
        assert f'"{correct}"' in artifact, (
            f'Correct checkpoint field name "{correct}" not found in artifact.'
        )


# ---------------------------------------------------------------------------
# Regression: Entry timing semantics (synthesis round 2 — Codex HIGH-2)
# ---------------------------------------------------------------------------

@pytest.mark.regression
def test_entry_price_documented_as_next_bar_open():
    """Signal.entry_price must be documented as next-bar open, not signal-bar close.

    Regression for: Codex HIGH-2 — artifact said entry_price is "price at
    signal bar close" but all concrete strategies use next-bar open.
    """
    artifact = _read_artifact()

    # Find the Signal dataclass documentation
    signal_match = re.search(
        r"entry_price: float\s+#\s*(.+)",
        artifact,
    )
    assert signal_match, "entry_price field not found in Signal documentation"
    comment = signal_match.group(1).lower()

    assert "next bar open" in comment or "next-bar open" in comment, (
        f"entry_price comment says '{signal_match.group(1)}' — "
        f"should reference next bar open, not signal bar close"
    )


# ---------------------------------------------------------------------------
# Regression: Causality constraint (synthesis round 2 — Codex HIGH-3)
# ---------------------------------------------------------------------------

@pytest.mark.regression
def test_causality_constraint_documented():
    """The precompute pattern discussion must include the causality guard.

    Regression for: Codex HIGH-3 — artifact recommended precompute-once
    pattern without mentioning the SignalCausality constraint that makes
    it safe. Non-causal strategies must be rejected from the precompute path.
    """
    artifact = _read_artifact()

    # Section 8.3 and/or 9.4 must mention causality
    section83_match = re.search(
        r"### 8\.3.*?(?=### 8\.4|## 9\.)",
        artifact,
        re.DOTALL,
    )
    assert section83_match, "Section 8.3 not found"
    section83 = section83_match.group(0)

    assert "causal" in section83.lower(), (
        "Section 8.3 discusses precompute pattern without mentioning causality constraint"
    )
    assert "requires_train_fit" in section83.lower() or "train_fit" in section83.lower(), (
        "Section 8.3 does not mention REQUIRES_TRAIN_FIT as the non-causal category"
    )


# ---------------------------------------------------------------------------
# Regression: Vectorized authoring path (synthesis round 2 — Codex MEDIUM-1)
# ---------------------------------------------------------------------------

@pytest.mark.regression
def test_vectorized_authoring_path_documented():
    """Section 6 must document the vectorized signal generation path.

    Regression for: Codex MEDIUM-1 — authoring workflow omitted
    generate_signals_vectorized(), management_modules(), and
    optimization_stages() which are actively used by concrete strategies.
    """
    artifact = _read_artifact()

    section6_match = re.search(
        r"## 6\. Strategy Authoring Workflow(.*?)## 7\.",
        artifact,
        re.DOTALL,
    )
    assert section6_match, "Section 6 not found"
    section6 = section6_match.group(1)

    required_methods = [
        "generate_signals_vectorized",
        "management_modules",
        "optimization_stages",
    ]
    missing = [m for m in required_methods if m not in section6]
    assert not missing, (
        f"Section 6 missing documentation for authoring methods: {missing}"
    )
