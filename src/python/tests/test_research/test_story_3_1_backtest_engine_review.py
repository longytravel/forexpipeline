"""Tests for Story 3.1: ClaudeBackTester Backtest Engine Baseline Review.

This is a research story — no production code. Tests validate the research
artifact exists on disk, has required sections, contains required content,
and satisfies all 11 acceptance criteria.
"""

import re
from pathlib import Path

import pytest

# Project root — file is at src/python/tests/test_research/test_story_3_1_...py
PROJECT_ROOT = Path(__file__).resolve().parents[4]
RESEARCH_ARTIFACT = (
    PROJECT_ROOT
    / "_bmad-output"
    / "planning-artifacts"
    / "research"
    / "backtest-engine-baseline-review.md"
)
STORY_FILE = (
    PROJECT_ROOT
    / "_bmad-output"
    / "implementation-artifacts"
    / "3-1-claudebacktester-backtest-engine-review.md"
)
STORY_2_1_ARTIFACT = (
    PROJECT_ROOT
    / "_bmad-output"
    / "planning-artifacts"
    / "research"
    / "strategy-evaluator-baseline-review.md"
)


@pytest.fixture
def artifact_text():
    """Load research artifact text."""
    assert RESEARCH_ARTIFACT.exists(), (
        f"Research artifact not found: {RESEARCH_ARTIFACT}"
    )
    return RESEARCH_ARTIFACT.read_text(encoding="utf-8")


@pytest.fixture
def story_text():
    """Load story file text."""
    assert STORY_FILE.exists(), f"Story file not found: {STORY_FILE}"
    return STORY_FILE.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Unit tests — artifact structure and content validation
# ---------------------------------------------------------------------------


class TestArtifactStructure:
    """Verify research artifact has all required sections (AC #1)."""

    REQUIRED_SECTIONS = [
        "Executive Summary",
        "Module Inventory",
        "Component Verdict Table",
        "Detailed Component Analysis",
        "PyO3 Bridge & Data Flow",
        "Optimization Engine Architecture",
        "Validation Pipeline Architecture",
        "Gap Analysis",
        "Proposed Architecture Updates",
    ]

    def test_artifact_exists(self):
        assert RESEARCH_ARTIFACT.exists()

    def test_artifact_not_empty(self, artifact_text):
        assert len(artifact_text) > 10000, "Artifact too short for comprehensive review"

    @pytest.mark.parametrize("section", REQUIRED_SECTIONS)
    def test_required_section_present(self, artifact_text, section):
        assert section.lower() in artifact_text.lower(), (
            f"Missing required section: {section}"
        )

    def test_appendix_a_parameter_layout(self, artifact_text):
        assert "Appendix A" in artifact_text
        assert "PL_SL_MODE" in artifact_text
        assert "PL_SIGNAL_P0" in artifact_text

    def test_appendix_b_metrics_reference(self, artifact_text):
        assert "Appendix B" in artifact_text
        assert "M_QUALITY" in artifact_text
        assert "M_SHARPE" in artifact_text

    def test_appendix_c_checkpoint_format(self, artifact_text):
        assert "Appendix C" in artifact_text
        assert "PipelineState" in artifact_text

    def test_appendix_d_cross_reference(self, artifact_text):
        assert "Appendix D" in artifact_text
        assert "Story 2-1" in artifact_text


class TestBaselineTraceability:
    """Verify baseline traceability (AC #1 prerequisite)."""

    def test_repo_path_documented(self, artifact_text):
        assert "ClaudeBackTester" in artifact_text

    def test_branch_documented(self, artifact_text):
        assert "master" in artifact_text

    def test_commit_hash_documented(self, artifact_text):
        assert "012ae57" in artifact_text or "2084beb" in artifact_text


class TestModuleInventory:
    """Verify module inventory completeness (AC #1)."""

    RUST_FILES = [
        "lib.rs",
        "constants.rs",
        "metrics.rs",
        "trade_basic.rs",
        "trade_full.rs",
        "sl_tp.rs",
        "filter.rs",
    ]

    PYTHON_CORE_FILES = [
        "engine.py",
        "encoding.py",
        "rust_loop.py",
        "dtypes.py",
        "metrics.py",
    ]

    OPTIMIZER_FILES = [
        "staged.py",
        "sampler.py",
        "run.py",
        "cv_objective.py",
        "ranking.py",
        "prefilter.py",
        "archive.py",
    ]

    PIPELINE_FILES = [
        "runner.py",
        "checkpoint.py",
        "confidence.py",
        "walk_forward.py",
        "monte_carlo.py",
        "cpcv.py",
        "regime.py",
        "stability.py",
        "types.py",
    ]

    @pytest.mark.parametrize("filename", RUST_FILES)
    def test_rust_file_inventoried(self, artifact_text, filename):
        assert filename in artifact_text, f"Rust file not inventoried: {filename}"

    @pytest.mark.parametrize("filename", PYTHON_CORE_FILES)
    def test_python_core_file_inventoried(self, artifact_text, filename):
        assert filename in artifact_text, f"Python core file not inventoried: {filename}"

    @pytest.mark.parametrize("filename", OPTIMIZER_FILES)
    def test_optimizer_file_inventoried(self, artifact_text, filename):
        assert filename in artifact_text, f"Optimizer file not inventoried: {filename}"

    @pytest.mark.parametrize("filename", PIPELINE_FILES)
    def test_pipeline_file_inventoried(self, artifact_text, filename):
        assert filename in artifact_text, f"Pipeline file not inventoried: {filename}"


class TestPyO3BridgeSpec:
    """Verify PyO3 Bridge & Data Flow specification (AC #2)."""

    def test_batch_evaluate_signature(self, artifact_text):
        assert "batch_evaluate" in artifact_text
        assert "PyReadonlyArray" in artifact_text or "param_matrix" in artifact_text

    def test_64_slot_parameter_layout(self, artifact_text):
        assert "64" in artifact_text
        assert "PL_SL_MODE" in artifact_text
        assert "PL_TP_MODE" in artifact_text

    def test_rayon_parallelism_documented(self, artifact_text):
        assert "rayon" in artifact_text
        assert "par_iter" in artifact_text or "parallel" in artifact_text.lower()

    def test_memory_model_documented(self, artifact_text):
        text_lower = artifact_text.lower()
        assert "zero-copy" in text_lower or "zero copy" in text_lower
        assert "metrics_out" in artifact_text

    def test_exec_mode_documented(self, artifact_text):
        assert "EXEC_BASIC" in artifact_text
        assert "EXEC_FULL" in artifact_text

    def test_sub_bar_data_flow(self, artifact_text):
        assert "sub_high" in artifact_text or "sub-bar" in artifact_text.lower()
        assert "h1_to_sub_start" in artifact_text or "M1" in artifact_text

    def test_d1_assessment(self, artifact_text):
        text_lower = artifact_text.lower()
        assert "d1" in text_lower
        assert "arrow ipc" in text_lower or "multi-process" in text_lower

    def test_nfr1_assessment(self, artifact_text):
        assert "NFR1" in artifact_text or "CPU utilization" in artifact_text


class TestPythonOrchestration:
    """Verify Python orchestration lifecycle (AC #3)."""

    def test_engine_lifecycle(self, artifact_text):
        assert "BacktestEngine" in artifact_text
        assert "signal precomputation" in artifact_text.lower() or "precompute" in artifact_text.lower()

    def test_encoding_documented(self, artifact_text):
        assert "EncodingSpec" in artifact_text or "encoding" in artifact_text.lower()
        assert "PL_" in artifact_text

    def test_signal_flow(self, artifact_text):
        text_lower = artifact_text.lower()
        assert "signal" in text_lower
        assert "precompute" in text_lower or "generate" in text_lower

    def test_data_marshalling(self, artifact_text):
        text_lower = artifact_text.lower()
        assert "numpy" in text_lower or "marshalling" in text_lower


class TestOptimizationEngine:
    """Verify optimization engine specification (AC #4)."""

    def test_staged_model(self, artifact_text):
        text_lower = artifact_text.lower()
        assert "staged" in text_lower
        assert "signal" in text_lower and "risk" in text_lower

    def test_sampling_strategies(self, artifact_text):
        assert "Sobol" in artifact_text
        assert "EDA" in artifact_text

    def test_cv_objective(self, artifact_text):
        text_lower = artifact_text.lower()
        assert "cross-validation" in text_lower or "cv" in text_lower

    def test_ranking(self, artifact_text):
        assert "rank" in artifact_text.lower()
        assert "DSR" in artifact_text or "Deflated Sharpe" in artifact_text

    def test_fr23_fr28_assessment(self, artifact_text):
        for fr in ["FR23", "FR24"]:
            assert fr in artifact_text, f"Missing optimization requirement: {fr}"


class TestValidationPipeline:
    """Verify validation pipeline specification (AC #5)."""

    VALIDATION_STAGES = [
        "walk-forward",
        "cpcv",
        "monte carlo",
        "regime",
        "stability",
        "confidence",
    ]

    @pytest.mark.parametrize("stage", VALIDATION_STAGES)
    def test_validation_stage_documented(self, artifact_text, stage):
        assert stage.lower() in artifact_text.lower(), (
            f"Validation stage not documented: {stage}"
        )

    def test_confidence_scoring_model(self, artifact_text):
        assert "RED" in artifact_text
        assert "YELLOW" in artifact_text
        assert "GREEN" in artifact_text

    def test_fr29_fr35_assessment(self, artifact_text):
        for fr in ["FR29", "FR30", "FR31", "FR32", "FR33", "FR34"]:
            assert fr in artifact_text, f"Missing validation requirement: {fr}"


class TestPipelineOrchestration:
    """Verify pipeline orchestration and checkpoint spec (AC #6)."""

    def test_runner_stage_sequencing(self, artifact_text):
        text_lower = artifact_text.lower()
        assert "stage" in text_lower
        assert "sequential" in text_lower or "sequencing" in text_lower

    def test_checkpoint_format(self, artifact_text):
        assert "checkpoint" in artifact_text.lower()
        assert "JSON" in artifact_text
        assert "atomic" in artifact_text.lower()

    def test_resume_logic(self, artifact_text):
        assert "resume" in artifact_text.lower()
        assert "completed_stages" in artifact_text

    def test_d3_assessment(self, artifact_text):
        assert "D3" in artifact_text

    def test_nfr5_assessment(self, artifact_text):
        assert "NFR5" in artifact_text or "checkpoint" in artifact_text.lower()

    @pytest.mark.regression
    def test_persisted_vs_recomputed_documented(self, artifact_text):
        """Regression: AC6 requires explicit persisted vs recomputed documentation."""
        text_lower = artifact_text.lower()
        assert "persisted" in text_lower and "recomputed" in text_lower, (
            "AC6 requires documenting what state is persisted vs recomputed on resume"
        )
        # Must mention both categories with concrete examples
        assert "backtest" in text_lower or "engine" in text_lower, (
            "Persisted-vs-recomputed must mention engine recomputation"
        )


class TestMetricsAndStorage:
    """Verify metrics and storage specification (AC #7)."""

    REQUIRED_METRICS = [
        "M_TRADES",
        "M_WIN_RATE",
        "M_PROFIT_FACTOR",
        "M_SHARPE",
        "M_SORTINO",
        "M_MAX_DD",
        "M_RETURN_PCT",
        "M_R_SQUARED",
        "M_ULCER",
        "M_QUALITY",
    ]

    def test_ten_metrics_documented(self, artifact_text):
        count = sum(1 for m in self.REQUIRED_METRICS if m in artifact_text)
        assert count >= 10, f"Only {count}/10 metrics documented"

    def test_d2_assessment(self, artifact_text):
        assert "D2" in artifact_text
        assert "Arrow IPC" in artifact_text or "SQLite" in artifact_text or "Parquet" in artifact_text

    def test_fr15_assessment(self, artifact_text):
        """FR15: equity curve, per-trade details, key metrics."""
        text_lower = artifact_text.lower()
        assert "equity curve" in text_lower
        assert "per-trade" in text_lower or "pnl_pips" in text_lower


class TestComponentVerdictTable:
    """Verify component verdict table (AC #8)."""

    REQUIRED_VERDICTS = ["Keep", "Adapt", "Replace", "Build New"]

    def test_verdict_table_exists(self, artifact_text):
        assert "Component Verdict Table" in artifact_text

    @pytest.mark.parametrize("verdict", REQUIRED_VERDICTS)
    def test_verdict_type_present(self, artifact_text, verdict):
        assert verdict.lower() in artifact_text.lower(), (
            f"Missing verdict type: {verdict}"
        )

    def test_v1_port_boundary_column(self, artifact_text):
        assert "port-now" in artifact_text
        assert "wrap-for-V1" in artifact_text
        assert "do-not-port" in artifact_text

    def test_rationale_cites_architecture(self, artifact_text):
        for decision in ["D1", "D2", "D3", "D13", "D14"]:
            assert decision in artifact_text, (
                f"Verdict rationale missing architecture decision: {decision}"
            )


class TestGapAnalysis:
    """Verify gap analysis (AC #9)."""

    def test_baseline_not_required(self, artifact_text):
        text_lower = artifact_text.lower()
        assert "not required" in text_lower or "not present in baseline" in text_lower or "gaps to build" in text_lower

    def test_architectural_shifts(self, artifact_text):
        text_lower = artifact_text.lower()
        assert "pyo3" in text_lower and "multi-process" in text_lower
        assert "state machine" in text_lower
        assert "session-aware" in text_lower or "cost model" in text_lower

    def test_superior_baseline_patterns(self, artifact_text):
        text_lower = artifact_text.lower()
        assert "precompute-once" in text_lower or "precompute once" in text_lower
        assert "shared engine" in text_lower or "single backtest" in text_lower.replace("\n", " ")


class TestProposedArchitectureUpdates:
    """Verify proposed architecture updates (AC #10)."""

    def test_proposals_in_artifact_not_architecture(self, artifact_text):
        assert "Proposed Architecture Updates" in artifact_text

    def test_at_least_one_proposal(self, artifact_text):
        assert "9.1" in artifact_text or "Proposal" in artifact_text


class TestDownstreamHandoff:
    """Verify downstream handoff sections (AC #11)."""

    DOWNSTREAM_STORIES = [
        "3-2", "3-3", "3-4", "3-5", "3-6", "3-7", "3-8", "3-9",
    ]

    def test_downstream_handoff_section_exists(self, artifact_text):
        assert "Downstream Handoff" in artifact_text

    @pytest.mark.parametrize("story", DOWNSTREAM_STORIES)
    def test_downstream_story_has_subsection(self, artifact_text, story):
        # Story references can be 3-2, 3.2, or Story 3-2
        assert story in artifact_text or story.replace("-", ".") in artifact_text, (
            f"Missing downstream handoff for Story {story}"
        )

    def test_v1_port_boundary_summary(self, artifact_text):
        assert "V1 Port Boundary" in artifact_text
        assert "port-now" in artifact_text
        assert "wrap-for-V1" in artifact_text

    @pytest.mark.regression
    @pytest.mark.parametrize("story", DOWNSTREAM_STORIES)
    def test_downstream_story_has_required_fields(self, artifact_text, story):
        """Regression: AC11 requires each downstream story to have all required subsections."""
        # Find the section for this story
        story_dot = story.replace("-", ".")
        # Look for the story section and extract it
        markers = [f"Story {story}", f"Story {story_dot}"]
        found = False
        for marker in markers:
            idx = artifact_text.find(f"### {marker}")
            if idx == -1:
                idx = artifact_text.find(marker)
            if idx != -1:
                # Find next ### section or end
                next_section = artifact_text.find("\n### ", idx + 1)
                if next_section == -1:
                    next_section = artifact_text.find("\n## ", idx + 1)
                if next_section == -1:
                    next_section = len(artifact_text)
                section_text = artifact_text[idx:next_section].lower()
                found = True
                break
        assert found, f"Could not find downstream handoff section for Story {story}"
        # AC11 requires: interface candidates / extracted, migration boundary,
        # V1 port decisions, deferred/no-port items, open questions
        assert "migration boundary" in section_text or "extracted from this review" in section_text, (
            f"Story {story} handoff missing migration boundary or extracted content"
        )
        assert "v1 port" in section_text or "port decision" in section_text or "port-now" in section_text or "no baseline" in section_text, (
            f"Story {story} handoff missing V1 port decisions"
        )

    @pytest.mark.regression
    def test_max_spread_pips_documents_rust_enforcement(self, artifact_text):
        """Regression: max_spread_pips is enforced in Rust batch_evaluate(), not just Python."""
        text_lower = artifact_text.lower()
        # Find the max_spread_pips discussion
        idx = text_lower.find("max_spread_pips")
        assert idx != -1, "max_spread_pips not documented"
        # The surrounding context should mention Rust enforcement
        context = text_lower[max(0, idx - 200):idx + 500]
        assert "rust" in context or "lib.rs" in context or "batch_evaluate" in context, (
            "max_spread_pips documentation must mention Rust-side enforcement (lib.rs:319-324)"
        )


class TestStoryCompletion:
    """Verify story file is properly completed."""

    def test_all_tasks_checked(self, story_text):
        unchecked = re.findall(r"- \[ \]", story_text)
        assert len(unchecked) == 0, (
            f"Found {len(unchecked)} unchecked tasks in story file"
        )

    def test_status_is_review(self, story_text):
        assert "Status: review" in story_text

    def test_dev_agent_record_populated(self, story_text):
        assert "Completion Notes List" in story_text
        idx = story_text.index("Completion Notes List")
        after = story_text[idx : idx + 500]
        assert "research artifact" in after.lower() or "comprehensive" in after.lower()

    def test_file_list_populated(self, story_text):
        idx = story_text.index("### File List")
        after = story_text[idx : idx + 500]
        assert "backtest-engine-baseline-review.md" in after


class TestCrossReferenceWithStory2_1:
    """Verify cross-reference with Story 2-1 (avoids duplication)."""

    def test_story_2_1_referenced(self, artifact_text):
        assert "Story 2-1" in artifact_text

    def test_no_indicator_catalogue_duplication(self, artifact_text):
        # Story 2-1 documented 18 indicators — we should NOT have a full catalogue
        assert "### 5.1 Simple Moving Average" not in artifact_text, (
            "Indicator catalogue duplicated from Story 2-1"
        )

    def test_story_2_1_artifact_exists(self):
        assert STORY_2_1_ARTIFACT.exists(), (
            "Story 2-1 research artifact should exist for cross-reference"
        )


# ---------------------------------------------------------------------------
# Live tests — verify real artifacts on disk
# ---------------------------------------------------------------------------


@pytest.mark.live
class TestLiveResearchArtifact:
    """Live test: verify the research artifact exists on disk and is valid."""

    def test_live_artifact_exists_on_disk(self):
        """The research artifact file must exist at the expected path."""
        assert RESEARCH_ARTIFACT.exists(), (
            f"Research artifact missing: {RESEARCH_ARTIFACT}"
        )
        size = RESEARCH_ARTIFACT.stat().st_size
        assert size > 20000, f"Artifact suspiciously small: {size} bytes"

    def test_live_artifact_readable_utf8(self):
        """Artifact must be valid UTF-8 markdown."""
        text = RESEARCH_ARTIFACT.read_text(encoding="utf-8")
        assert text.startswith("#"), "Artifact should start with markdown heading"

    def test_live_artifact_nine_sections(self):
        """Artifact must have all 9 main sections."""
        text = RESEARCH_ARTIFACT.read_text(encoding="utf-8")
        sections = re.findall(r"^## \d+\.", text, re.MULTILINE)
        assert len(sections) >= 9, (
            f"Expected 9 numbered sections, found {len(sections)}: {sections}"
        )

    def test_live_artifact_four_appendices(self):
        """Artifact must have 4 appendices (A-D)."""
        text = RESEARCH_ARTIFACT.read_text(encoding="utf-8")
        for appendix in ["Appendix A", "Appendix B", "Appendix C", "Appendix D"]:
            assert appendix in text, f"Missing {appendix}"

    def test_live_component_verdict_table_complete(self):
        """Verdict table must have all verdict types and V1 port boundaries."""
        text = RESEARCH_ARTIFACT.read_text(encoding="utf-8")
        assert "| **Rust trade simulation**" in text, "Missing key component in verdict table"
        assert "port-now" in text
        assert "wrap-for-V1" in text
        assert "do-not-port" in text

    def test_live_downstream_handoff_all_stories(self):
        """Downstream handoff must cover Stories 3-2 through 3-9."""
        text = RESEARCH_ARTIFACT.read_text(encoding="utf-8")
        for story in ["3-2", "3-3", "3-4", "3-5", "3-6", "3-7", "3-8", "3-9"]:
            assert f"Story {story}" in text, (
                f"Missing downstream handoff for Story {story}"
            )

    def test_live_gap_analysis_four_shifts(self):
        """Gap analysis must document 4 architectural shifts."""
        text = RESEARCH_ARTIFACT.read_text(encoding="utf-8")
        text_lower = text.lower()
        assert "pyo3" in text_lower, "Missing PyO3→multi-process shift"
        assert "state machine" in text_lower, "Missing runner→state machine shift"
        assert "session-aware" in text_lower, "Missing flat cost→session-aware shift"
        assert "strategy_engine" in text_lower, "Missing monolithic→crate separation shift"

    def test_live_proposed_architecture_updates(self):
        """Must have at least 2 proposed architecture updates."""
        text = RESEARCH_ARTIFACT.read_text(encoding="utf-8")
        proposals = re.findall(r"### 9\.\d", text)
        assert len(proposals) >= 2, (
            f"Expected >=2 architecture proposals, found {len(proposals)}"
        )

    def test_live_story_file_complete(self):
        """Story file must have all tasks checked and status=review."""
        text = STORY_FILE.read_text(encoding="utf-8")
        unchecked = re.findall(r"- \[ \]", text)
        assert len(unchecked) == 0, (
            f"{len(unchecked)} unchecked tasks remain in story file"
        )
        assert "Status: review" in text

    def test_live_all_eleven_acs_addressed(self):
        """All 11 acceptance criteria must be addressable from artifact content."""
        text = RESEARCH_ARTIFACT.read_text(encoding="utf-8")
        text_lower = text.lower()

        # AC1: Module inventory produced
        assert "module inventory" in text_lower

        # AC2: PyO3 Bridge & Data Flow specification
        assert "batch_evaluate" in text and "pyo3" in text_lower

        # AC3: Python orchestration lifecycle
        assert "backtestengine" in text_lower or "backtest engine" in text_lower

        # AC4: Optimization engine specification
        assert "staged" in text_lower and "sampler" in text_lower

        # AC5: Validation pipeline specification
        assert "walk-forward" in text_lower or "walk forward" in text_lower
        assert "cpcv" in text_lower
        assert "monte carlo" in text_lower

        # AC6: Pipeline orchestration specification
        assert "checkpoint" in text_lower and "resume" in text_lower

        # AC7: Metrics and storage specification
        assert "m_trades" in text_lower and "m_quality" in text_lower

        # AC8: Component verdict table
        assert "verdict" in text_lower
        assert "keep" in text_lower and "adapt" in text_lower and "replace" in text_lower

        # AC9: Gap analysis
        assert "gap analysis" in text_lower
        assert "arrow ipc" in text_lower

        # AC10: Proposed architecture updates
        assert "proposed architecture updates" in text_lower

        # AC11: Downstream handoff
        assert "downstream handoff" in text_lower
        assert "story 3-2" in text_lower or "story 3.2" in text_lower

    def test_live_cross_reference_story_2_1_exists(self):
        """Story 2-1 research artifact must exist for cross-reference integrity."""
        assert STORY_2_1_ARTIFACT.exists(), (
            f"Story 2-1 artifact missing for cross-reference: {STORY_2_1_ARTIFACT}"
        )
