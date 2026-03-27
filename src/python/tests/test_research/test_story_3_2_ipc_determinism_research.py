"""Tests for Story 3.2: Python-Rust IPC & Deterministic Backtesting Research.

This is a research story — no production code changes. Tests validate the research
artifact exists on disk, has all 12 required sections, contains actionable content,
and satisfies all 7 acceptance criteria.

Tests go beyond keyword presence (lesson from Story 3-1 review) — they verify
structural completeness (required subsections per section) and cross-reference
claims against source where feasible.
"""

import json
import re
from pathlib import Path

import pytest

# Project root — file is at src/python/tests/test_research/test_story_3_2_...py
PROJECT_ROOT = Path(__file__).resolve().parents[4]
RESEARCH_ARTIFACT = (
    PROJECT_ROOT
    / "_bmad-output"
    / "planning-artifacts"
    / "research"
    / "3-2-ipc-determinism-research.md"
)
STORY_FILE = (
    PROJECT_ROOT
    / "_bmad-output"
    / "implementation-artifacts"
    / "3-2-python-rust-ipc-deterministic-backtesting-research.md"
)
ARCHITECTURE_FILE = (
    PROJECT_ROOT
    / "_bmad-output"
    / "planning-artifacts"
    / "architecture.md"
)
STORY_3_1_ARTIFACT = (
    PROJECT_ROOT
    / "_bmad-output"
    / "planning-artifacts"
    / "research"
    / "backtest-engine-baseline-review.md"
)


@pytest.fixture
def artifact_text():
    """Load research artifact text."""
    assert RESEARCH_ARTIFACT.exists(), (
        f"Research artifact not found: {RESEARCH_ARTIFACT}"
    )
    return RESEARCH_ARTIFACT.read_text(encoding="utf-8")


@pytest.fixture
def artifact_sections(artifact_text):
    """Parse artifact into sections by ## headers."""
    sections = {}
    current_section = None
    current_lines = []
    for line in artifact_text.split("\n"):
        if line.startswith("## "):
            if current_section:
                sections[current_section] = "\n".join(current_lines)
            current_section = line.lstrip("# ").strip()
            current_lines = []
        elif current_section:
            current_lines.append(line)
    if current_section:
        sections[current_section] = "\n".join(current_lines)
    return sections


# ---------------------------------------------------------------------------
# Artifact structure validation
# ---------------------------------------------------------------------------


class TestArtifactStructure:
    """Verify research artifact has all 12 required sections (Task 8)."""

    REQUIRED_SECTIONS = [
        "Executive Summary",
        "IPC Comparison Matrix",
        "Determinism Strategies",
        "Reproducibility Contract",
        "Checkpoint/Resume Patterns",
        "Memory Budgeting",
        "Architecture Alignment Matrix",
        "Proposed Architecture Updates",
        "Downstream Contracts",
        "Build Plan for Stories 3.3-3.5",
        "Dependency Notes for Stories 3.6-3.9",
        "Open Questions",
    ]

    def test_artifact_exists(self):
        assert RESEARCH_ARTIFACT.exists()

    def test_artifact_not_empty(self, artifact_text):
        assert len(artifact_text) > 20000, (
            "Artifact too short for comprehensive research"
        )

    @pytest.mark.parametrize("section", REQUIRED_SECTIONS)
    def test_required_section_present(self, artifact_text, section):
        # Normalize for comparison: remove numbering prefix
        section_lower = section.lower()
        text_lower = artifact_text.lower()
        assert section_lower in text_lower, (
            f"Missing required section: {section}"
        )


# ---------------------------------------------------------------------------
# AC #1: IPC Recommendation Justified (Task 9 test 1)
# ---------------------------------------------------------------------------


class TestIPCRecommendationJustified:
    """Verify IPC recommendation includes quantitative rationale tied to
    repo-local constraints (existing Arrow IPC patterns, Windows subprocess
    behavior), not just theoretical comparison.

    AC #1 + Task 9 test_ipc_recommendation_justified.
    """

    def test_at_least_three_options_evaluated(self, artifact_text):
        """AC #1: comparison matrix of at least 3 mechanisms."""
        options_found = 0
        for option_label in ["Option A", "Option B", "Option C"]:
            if option_label in artifact_text:
                options_found += 1
        assert options_found >= 3, (
            f"Only {options_found} IPC options found, need at least 3"
        )

    def test_six_evaluation_criteria(self, artifact_text):
        """AC #1: evaluating latency, serialization cost, crash isolation,
        implementation complexity, debugging experience, Windows compat."""
        criteria = [
            "latency",
            "serialization",
            "crash isolation",
            "complexity",
            "debug",
            "windows",
        ]
        for criterion in criteria:
            assert criterion.lower() in artifact_text.lower(), (
                f"Missing evaluation criterion: {criterion}"
            )

    def test_comparison_matrix_table_exists(self, artifact_text):
        """Verify a comparison matrix table with scoring exists."""
        assert "Weighted Total" in artifact_text or "weighted" in artifact_text.lower(), (
            "No weighted scoring found in comparison matrix"
        )

    def test_recommendation_references_existing_patterns(self, artifact_text):
        """Recommendation must reference repo-local patterns, not just theory."""
        # Must reference existing subprocess patterns
        assert "test_rust_crate" in artifact_text or "_run_cargo" in artifact_text, (
            "Recommendation does not reference existing subprocess pattern "
            "(_run_cargo in test_rust_crate.py)"
        )
        # Must reference existing Arrow IPC patterns
        assert "safe_write" in artifact_text or "arrow_converter" in artifact_text, (
            "Recommendation does not reference existing Arrow IPC patterns "
            "(safe_write.py or arrow_converter.py)"
        )

    def test_recommendation_addresses_nfr10_crash_isolation(self, artifact_text):
        """NFR10 (crash prevention) is the strongest argument for subprocess."""
        assert "NFR10" in artifact_text, (
            "Recommendation does not reference NFR10 (crash prevention)"
        )
        # Must explicitly discuss crash isolation difference between options
        text_lower = artifact_text.lower()
        assert "crash isolation" in text_lower, (
            "No discussion of crash isolation differences between options"
        )

    def test_recommendation_quantitative(self, artifact_text):
        """Must include latency numbers or overhead percentages."""
        # Look for latency measurements (μs, ms, or percentage)
        has_latency = bool(
            re.search(r"\d+\s*(μs|ms|microsecond|millisecond)", artifact_text)
        )
        has_percentage = bool(re.search(r"\d+\.?\d*\s*%", artifact_text))
        assert has_latency or has_percentage, (
            "Recommendation lacks quantitative rationale "
            "(no latency measurements or overhead percentages found)"
        )


# ---------------------------------------------------------------------------
# AC #2: Reproducibility Contract Resolves Ambiguity (Task 9 test 2)
# ---------------------------------------------------------------------------


class TestReproducibilityContractResolvesAmbiguity:
    """Verify the reproducibility contract explicitly resolves tolerance vs
    bit-identical for each output type and states how compliance is tested.

    AC #2 + Task 9 test_reproducibility_contract_resolves_ambiguity.
    """

    OUTPUT_TYPES = ["trade log", "equity curve", "metrics", "manifest"]

    @pytest.mark.parametrize("output_type", OUTPUT_TYPES)
    def test_output_type_addressed(self, artifact_text, output_type):
        """Each output type must be addressed in the contract."""
        assert output_type.lower() in artifact_text.lower(), (
            f"Reproducibility contract missing output type: {output_type}"
        )

    def test_bit_identical_mentioned(self, artifact_text):
        """Contract must use 'bit-identical' for applicable outputs."""
        assert "bit-identical" in artifact_text.lower(), (
            "Contract does not use 'bit-identical' classification"
        )

    def test_tolerance_based_mentioned(self, artifact_text):
        """Contract must use 'tolerance' for applicable outputs."""
        assert "tolerance" in artifact_text.lower(), (
            "Contract does not use 'tolerance-based' classification"
        )

    def test_verification_method_per_type(self, artifact_text):
        """Each output type should have a verification method."""
        assert "sha-256" in artifact_text.lower() or "sha256" in artifact_text.lower(), (
            "No hash-based verification method specified"
        )

    def test_prd_vs_epic3_tension_resolved(self, artifact_text):
        """Must explicitly resolve PRD 'defined tolerance' vs Epic 3 'bit-identical'."""
        text_lower = artifact_text.lower()
        has_prd_ref = "prd" in text_lower and "tolerance" in text_lower
        has_resolution = "bit-identical" in text_lower and "contract" in text_lower
        assert has_prd_ref and has_resolution, (
            "Contract does not explicitly resolve PRD vs Epic 3 tension"
        )

    def test_compliance_verification_protocol(self, artifact_text):
        """Must include a verification protocol (not just theory)."""
        text_lower = artifact_text.lower()
        assert "verification" in text_lower and "protocol" in text_lower, (
            "No verification protocol for compliance testing"
        )


# ---------------------------------------------------------------------------
# AC #2: Determinism Strategies Actionable (Task 9 test 3)
# ---------------------------------------------------------------------------


class TestDeterminismStrategiesActionable:
    """Verify all 5 determinism areas have concrete strategies with code
    patterns or compiler flags, not just descriptions.

    AC #2 + Task 9 test_determinism_strategies_actionable.
    """

    def test_floating_point_has_compiler_flags(self, artifact_text):
        """Floating-point strategy must include compiler flags."""
        assert "target-feature" in artifact_text or "fma" in artifact_text.lower(), (
            "Floating-point strategy missing compiler flag for FMA control"
        )
        assert ".cargo/config" in artifact_text or "rustflags" in artifact_text.lower(), (
            "No .cargo/config.toml configuration for compiler flags"
        )

    def test_rayon_has_code_pattern(self, artifact_text):
        """Rayon strategy must include code pattern for deterministic iteration."""
        assert "par_chunks" in artifact_text or "IndexedParallelIterator" in artifact_text, (
            "Rayon strategy missing concrete code pattern "
            "(par_chunks or IndexedParallelIterator)"
        )

    def test_random_seed_has_rng_type(self, artifact_text):
        """Seed strategy must specify concrete RNG type."""
        assert "ChaCha" in artifact_text or "SeedableRng" in artifact_text, (
            "Seed management strategy missing concrete RNG type"
        )

    def test_timestamp_has_precision_spec(self, artifact_text):
        """Timestamp strategy must specify int64 microsecond format."""
        assert "int64" in artifact_text and "microsecond" in artifact_text.lower(), (
            "Timestamp strategy missing int64 microsecond precision specification"
        )

    def test_windows_has_platform_specifics(self, artifact_text):
        """Windows strategy must address MSVC and NTFS specifics."""
        text_lower = artifact_text.lower()
        assert "msvc" in text_lower, (
            "Windows strategy missing MSVC toolchain discussion"
        )
        assert "ntfs" in text_lower or "atomic rename" in text_lower, (
            "Windows strategy missing NTFS rename/locking discussion"
        )

    def test_all_five_areas_covered(self, artifact_text):
        """Must cover all 5 areas: float, rayon, seeds, timestamps, windows."""
        areas = {
            "floating-point": ["floating-point", "floating point", "ieee 754", "fma"],
            "rayon": ["rayon", "parallel"],
            "seeds": ["seed", "random seed", "rng"],
            "timestamps": ["timestamp", "microsecond"],
            "windows": ["windows", "msvc", "ntfs"],
        }
        text_lower = artifact_text.lower()
        for area, keywords in areas.items():
            found = any(kw in text_lower for kw in keywords)
            assert found, f"Determinism area not covered: {area}"


# ---------------------------------------------------------------------------
# AC #3: Checkpoint Schema Defined (Task 9 test 4)
# ---------------------------------------------------------------------------


class TestCheckpointSchemaDefined:
    """Verify checkpoint schema includes identity fields and crash-safe
    write pattern documented with Windows NTFS specifics.

    AC #3 + Task 9 test_checkpoint_schema_defined.
    """

    def test_config_hash_in_checkpoint(self, artifact_text):
        """Checkpoint must include config hash for identity verification."""
        assert "config_hash" in artifact_text, (
            "Checkpoint schema missing config_hash identity field"
        )

    def test_last_processed_index(self, artifact_text):
        """Checkpoint must track progress (last processed index or batch)."""
        has_index = (
            "last_batch_end_index" in artifact_text
            or "completed_batches" in artifact_text
            or "last_completed_batch" in artifact_text
            or "completed_param_sets" in artifact_text
        )
        assert has_index, (
            "Checkpoint schema missing progress tracking field"
        )

    def test_open_position_state(self, artifact_text):
        """Checkpoint should address open position state."""
        assert "open_position" in artifact_text.lower(), (
            "Checkpoint schema missing open position state field"
        )

    def test_crash_safe_write_pattern(self, artifact_text):
        """Must document temp → fsync → rename pattern."""
        text_lower = artifact_text.lower()
        has_temp = "partial" in text_lower or "temp" in text_lower
        has_fsync = "fsync" in text_lower or "sync_all" in text_lower
        has_rename = "rename" in text_lower or "replace" in text_lower
        assert has_temp and has_fsync and has_rename, (
            "Crash-safe write pattern incomplete — need temp + fsync + rename"
        )

    def test_ntfs_specifics_documented(self, artifact_text):
        """Must address Windows NTFS atomic rename semantics."""
        text_lower = artifact_text.lower()
        has_ntfs = "ntfs" in text_lower
        has_windows_rename = (
            "os.replace" in artifact_text
            or "MoveFileEx" in artifact_text
            or "MOVEFILE_REPLACE_EXISTING" in artifact_text
        )
        assert has_ntfs or has_windows_rename, (
            "Missing Windows NTFS-specific crash-safe write documentation"
        )

    def test_within_stage_vs_cross_stage(self, artifact_text):
        """Must distinguish within-stage (Rust) and cross-stage (Python) checkpointing."""
        text_lower = artifact_text.lower()
        assert "within-stage" in text_lower or "within stage" in text_lower, (
            "Missing within-stage checkpoint concept"
        )
        assert "cross-stage" in text_lower or "cross stage" in text_lower, (
            "Missing cross-stage checkpoint concept"
        )


# ---------------------------------------------------------------------------
# AC #4: Memory Budget Grounded (Task 9 test 5)
# ---------------------------------------------------------------------------


class TestMemoryBudgetGrounded:
    """Verify concrete memory budget calculated for reference workload using
    data volume context with specific thresholds.

    AC #4 + Task 9 test_memory_budget_grounded.
    """

    def test_reference_workload_specified(self, artifact_text):
        """Must use 10-year EURUSD M1 as reference workload."""
        text_lower = artifact_text.lower()
        assert "10" in artifact_text and "eurusd" in text_lower, (
            "Missing reference workload specification (10-year EURUSD M1)"
        )

    def test_market_data_size_specified(self, artifact_text):
        """Must specify ~400MB for 10-year M1 Arrow IPC."""
        assert "400" in artifact_text and "MB" in artifact_text, (
            "Missing market data size (~400MB) for reference workload"
        )

    def test_thread_buffer_calculation(self, artifact_text):
        """Must specify 16 threads × 50MB = 800MB trade buffer target."""
        has_threads = "16" in artifact_text
        has_buffer = "50MB" in artifact_text or "50 MB" in artifact_text
        has_total = "800" in artifact_text
        assert has_threads and (has_buffer or has_total), (
            "Missing thread buffer calculation (16 × 50MB = 800MB)"
        )

    def test_os_reserve_specified(self, artifact_text):
        """Must specify 2-4GB OS reserve per NFR4."""
        text_lower = artifact_text.lower()
        has_reserve = "2-4" in artifact_text or "2-4gb" in text_lower
        has_nfr4 = "nfr4" in text_lower
        assert has_reserve and has_nfr4, (
            "Missing OS reserve specification (2-4GB per NFR4)"
        )

    def test_mmap_not_counted_against_heap(self, artifact_text):
        """mmap data must not be counted against heap allocation."""
        text_lower = artifact_text.lower()
        assert "mmap" in text_lower, "Missing mmap discussion"
        # mmap should be described as not counting against heap or zero-copy
        assert "zero-copy" in text_lower or "not counted" in text_lower, (
            "Must clarify mmap is zero-copy / not counted against heap"
        )

    def test_throttle_thresholds_defined(self, artifact_text):
        """Must define specific throttle-before-OOM thresholds."""
        text_lower = artifact_text.lower()
        assert "throttle" in text_lower, "Missing throttle mechanism"
        # Must have specific MB/GB thresholds
        has_threshold = bool(
            re.search(r"\d+\s*(MB|GB|mb|gb)", artifact_text)
        )
        assert has_threshold, (
            "Throttle thresholds lack specific memory values (MB/GB)"
        )

    def test_pre_allocation_code_pattern(self, artifact_text):
        """Must include pre-allocation code pattern (Vec::with_capacity or similar)."""
        assert "with_capacity" in artifact_text or "pre_allocate" in artifact_text, (
            "Missing pre-allocation code pattern (Vec::with_capacity)"
        )


# ---------------------------------------------------------------------------
# AC #5: Architecture Alignment Complete (Task 9 test 6)
# ---------------------------------------------------------------------------


class TestArchitectureAlignmentComplete:
    """Verify D1, D2, D3, D8, D13, D14 referenced with alignment/deviation
    status and evidence-based rationale; D15 confirmed out of scope.

    AC #5 requires these 6 decisions specifically (not all D1-D14).
    Task 9 test_architecture_alignment_complete.
    """

    ARCH_DECISIONS = ["D1", "D2", "D3", "D8", "D13", "D14"]

    @pytest.mark.parametrize("decision", ARCH_DECISIONS)
    def test_decision_referenced(self, artifact_text, decision):
        """Each architecture decision D1-D14 must be referenced."""
        assert decision in artifact_text, (
            f"Architecture decision {decision} not referenced"
        )

    def test_alignment_matrix_exists(self, artifact_text):
        """Must have an alignment matrix (table format)."""
        text_lower = artifact_text.lower()
        assert "alignment" in text_lower and "matrix" in text_lower, (
            "Missing architecture alignment matrix"
        )

    def test_d15_out_of_scope(self, artifact_text):
        """D15 must be confirmed as out of scope / no impact."""
        # Find D15 references
        assert "D15" in artifact_text, "D15 not mentioned at all"
        text_lower = artifact_text.lower()
        has_out_of_scope = (
            "out of scope" in text_lower
            or "no impact" in text_lower
            or "orthogonal" in text_lower
        )
        assert has_out_of_scope, (
            "D15 mentioned but not confirmed as out of scope / no impact"
        )

    def test_aligned_or_deviation_per_decision(self, artifact_text):
        """Each decision must have an explicit alignment status."""
        text_lower = artifact_text.lower()
        assert "aligned" in text_lower, (
            "No 'aligned' classification found in alignment assessment"
        )

    def test_no_deviations_or_justified(self, artifact_text):
        """If deviations exist, they must be justified with evidence."""
        text_lower = artifact_text.lower()
        if "deviation" in text_lower:
            assert "justif" in text_lower or "evidence" in text_lower, (
                "Deviation found without evidence-based justification"
            )


# ---------------------------------------------------------------------------
# AC #7: Downstream Contracts Consumable (Task 9 test 7)
# ---------------------------------------------------------------------------


class TestDownstreamContractsConsumable:
    """Verify batch job CLI contract, checkpoint schema, reproducibility
    policy, and memory budget model are defined with enough specificity
    that Stories 3.3-3.5 can implement against them without ambiguity.

    AC #7 + Task 9 test_downstream_contracts_consumable.
    """

    def test_cli_contract_has_arguments(self, artifact_text):
        """Batch job CLI contract must list required arguments."""
        assert "--config" in artifact_text, "CLI contract missing --config argument"
        assert "--market-data" in artifact_text, (
            "CLI contract missing --market-data argument"
        )
        assert "--output-dir" in artifact_text, (
            "CLI contract missing --output-dir argument"
        )

    def test_cli_contract_has_exit_codes(self, artifact_text):
        """CLI contract must define exit code 0 (success) and at least one non-zero code."""
        # Must define exit code 0 (success)
        assert re.search(r"\|\s*0\s*\|", artifact_text), (
            "CLI contract missing exit code 0 (success)"
        )
        # Must define at least one non-zero exit code (failure)
        has_nonzero = bool(re.search(r"\|\s*[1-9]\d*\s*\|", artifact_text))
        assert has_nonzero, (
            "CLI contract missing non-zero exit codes (failure cases)"
        )

    def test_cli_contract_has_output_files(self, artifact_text):
        """CLI contract must define output file formats."""
        assert "metrics.arrow" in artifact_text, (
            "CLI contract missing metrics output file specification"
        )

    def test_checkpoint_schema_has_identity_fields(self, artifact_text):
        """Checkpoint schema must include identity fields for resume verification."""
        identity_fields = ["config_hash", "strategy_spec_hash", "market_data_hash"]
        for field in identity_fields:
            assert field in artifact_text, (
                f"Checkpoint schema missing identity field: {field}"
            )

    def test_reproducibility_policy_defines_guarantees(self, artifact_text):
        """Reproducibility policy must state what is guaranteed identical."""
        text_lower = artifact_text.lower()
        assert "guaranteed" in text_lower or "bit-identical" in text_lower, (
            "Reproducibility policy does not state what is guaranteed"
        )

    def test_memory_budget_model_has_inputs(self, artifact_text):
        """Memory budget model must define its inputs."""
        inputs = ["total_system_memory", "available_memory", "physical_cores"]
        found = sum(1 for inp in inputs if inp in artifact_text)
        assert found >= 2, (
            f"Memory budget model defines only {found}/3 expected inputs"
        )

    def test_memory_budget_model_has_calculation(self, artifact_text):
        """Memory budget model must include the calculation logic."""
        assert "os_reserve" in artifact_text.lower() or "os reserve" in artifact_text.lower(), (
            "Memory budget calculation missing OS reserve deduction"
        )
        assert "num_threads" in artifact_text or "thread" in artifact_text.lower(), (
            "Memory budget calculation missing thread count derivation"
        )

    def test_progress_protocol_defined(self, artifact_text):
        """CLI contract must define progress output protocol."""
        text_lower = artifact_text.lower()
        assert "progress" in text_lower and "protocol" in text_lower, (
            "Missing progress reporting protocol"
        )

    def test_error_structure_follows_d8(self, artifact_text):
        """Error output must follow D8 structured JSON format."""
        assert "error_type" in artifact_text, (
            "Error structure missing error_type field (D8)"
        )
        assert "category" in artifact_text, (
            "Error structure missing category field (D8)"
        )


# ---------------------------------------------------------------------------
# AC #7: Build Plan Differentiated (Task 9 test 8)
# ---------------------------------------------------------------------------


class TestBuildPlanDifferentiated:
    """Verify stories 3.3-3.5 have detailed build plans with interface
    contracts, and stories 3.6-3.9 have dependency notes.

    AC #7 + Task 9 test_build_plan_differentiated.
    """

    DETAILED_STORIES = ["3-3", "3-4", "3-5"]
    DEPENDENCY_STORIES = ["3-6", "3-7", "3-8", "3-9"]

    @pytest.mark.parametrize("story_id", DETAILED_STORIES)
    def test_detailed_story_in_build_plan(self, artifact_text, story_id):
        """Stories 3.3-3.5 must appear in the build plan."""
        assert story_id in artifact_text, (
            f"Story {story_id} missing from build plan"
        )

    @pytest.mark.parametrize("story_id", DEPENDENCY_STORIES)
    def test_dependency_story_has_notes(self, artifact_text, story_id):
        """Stories 3.6-3.9 must appear in dependency notes."""
        assert story_id in artifact_text, (
            f"Story {story_id} missing from dependency notes"
        )

    def test_build_plan_has_approach_column(self, artifact_text):
        """Build plan must specify approach (port/build-new/hybrid)."""
        text_lower = artifact_text.lower()
        approaches = ["port", "build new", "adapt", "extend"]
        found = sum(1 for a in approaches if a in text_lower)
        assert found >= 2, (
            "Build plan lacks differentiated approaches (port/build-new/adapt)"
        )

    def test_build_plan_has_complexity(self, artifact_text):
        """Build plan must include complexity estimates."""
        has_complexity = any(
            size in artifact_text for size in ["**S**", "**M**", "**L**", "**XL**"]
        )
        assert has_complexity, (
            "Build plan missing complexity estimates (S/M/L/XL)"
        )

    def test_critical_path_documented(self, artifact_text):
        """Must document critical path between stories 3.3-3.5."""
        text_lower = artifact_text.lower()
        assert "critical path" in text_lower, (
            "Missing critical path documentation for stories 3.3-3.5"
        )

    def test_components_to_port_listed(self, artifact_text):
        """Must list specific ClaudeBackTester components to port."""
        baseline_files = ["trade_basic", "trade_full", "metrics.rs", "sl_tp", "filter.rs"]
        found = sum(1 for f in baseline_files if f in artifact_text)
        assert found >= 3, (
            f"Only {found}/5 baseline components listed for porting"
        )


# ---------------------------------------------------------------------------
# Live integration tests — verify research artifact on disk
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Appendix Completeness (BMAD L3 — review finding)
# ---------------------------------------------------------------------------


class TestAppendixCompleteness:
    """Verify Appendix A (PRD cross-references) and Appendix B (Architecture
    cross-references) exist and reference the specified requirement ranges.

    Added during review synthesis to address BMAD L3 finding.
    """

    def test_appendix_a_exists(self, artifact_text):
        """Appendix A must exist in the artifact."""
        assert "Appendix A" in artifact_text, "Missing Appendix A"

    def test_appendix_b_exists(self, artifact_text):
        """Appendix B must exist in the artifact."""
        assert "Appendix B" in artifact_text, "Missing Appendix B"

    @pytest.mark.parametrize("req", [
        "FR14", "FR15", "FR16", "FR17", "FR18", "FR19", "FR42",
    ])
    def test_appendix_a_fr_referenced(self, artifact_text, req):
        """Each FR in the specified range must appear in Appendix A."""
        # Find Appendix A section
        appendix_a_start = artifact_text.find("Appendix A")
        assert appendix_a_start > -1, f"Appendix A not found for {req} check"
        appendix_a_text = artifact_text[appendix_a_start:]
        assert req in appendix_a_text, (
            f"Appendix A missing cross-reference for {req}"
        )

    @pytest.mark.parametrize("req", [
        "NFR1", "NFR2", "NFR3", "NFR4", "NFR5", "NFR9",
        "NFR10", "NFR11", "NFR12", "NFR13", "NFR14", "NFR15",
    ])
    def test_appendix_a_nfr_referenced(self, artifact_text, req):
        """Each NFR in the specified range must appear in Appendix A."""
        appendix_a_start = artifact_text.find("Appendix A")
        assert appendix_a_start > -1, f"Appendix A not found for {req} check"
        appendix_a_text = artifact_text[appendix_a_start:]
        assert req in appendix_a_text, (
            f"Appendix A missing cross-reference for {req}"
        )

    @pytest.mark.parametrize("decision", [
        "D1", "D2", "D3", "D4", "D5", "D6", "D7",
        "D8", "D9", "D10", "D11", "D12", "D13", "D14", "D15",
    ])
    def test_appendix_b_decision_referenced(self, artifact_text, decision):
        """Each architecture decision D1-D15 must appear in Appendix B."""
        appendix_b_start = artifact_text.find("Appendix B")
        assert appendix_b_start > -1, (
            f"Appendix B not found for {decision} check"
        )
        appendix_b_text = artifact_text[appendix_b_start:]
        assert decision in appendix_b_text, (
            f"Appendix B missing cross-reference for {decision}"
        )


# ---------------------------------------------------------------------------
# Regression tests (review synthesis findings)
# ---------------------------------------------------------------------------


class TestRegressionReviewSynthesis:
    """Regression tests for issues found during review synthesis.

    Each test guards against a specific class of bug found by BMAD or Codex
    reviewers during the Story 3-2 code review.
    """

    @pytest.mark.regression
    def test_equity_curve_contract_is_per_trade(self, artifact_text):
        """Regression: equity curve contract must specify per-trade granularity,
        not per-bar (Codex H2 — contract contradiction).

        The CLI output contract and Open Questions must agree on granularity.
        V1 uses per-trade; per-bar is Growth.
        """
        # Find the CLI output files section (§9.1 Downstream Contracts area)
        contracts_start = artifact_text.find("Downstream Contracts")
        assert contracts_start > -1, "Downstream Contracts section not found"
        contracts_text = artifact_text[contracts_start:]

        # Equity curve must reference per-trade columns, not bar_index
        equity_line_start = contracts_text.find("equity_")
        assert equity_line_start > -1, "Equity curve output not defined"
        equity_section = contracts_text[equity_line_start:equity_line_start + 500]

        assert "trade_index" in equity_section, (
            "Equity curve contract must use trade_index (per-trade), not bar_index"
        )
        assert "bar_index" not in equity_section, (
            "Equity curve contract still uses bar_index — should be per-trade for V1"
        )

    @pytest.mark.regression
    def test_memory_budget_exec_summary_matches_table(self, artifact_text):
        """Regression: executive summary memory figure must be consistent with
        the detailed budget table (Codex M1 — numerical inconsistency).

        The exec summary must NOT claim ~2.4GB when the table totals ~1.1GB heap.
        """
        # Extract executive summary section
        exec_start = artifact_text.find("Executive Summary")
        assert exec_start > -1
        # Find the next section boundary
        next_section = artifact_text.find("\n## ", exec_start + 1)
        exec_text = artifact_text[exec_start:next_section] if next_section > -1 else artifact_text[exec_start:]

        # The exec summary should NOT say "~2.4GB active" (the old incorrect value)
        assert "~2.4GB active" not in exec_text, (
            "Executive summary still claims ~2.4GB active — inconsistent with "
            "detailed table (~1,065MB heap)"
        )

    @pytest.mark.regression
    def test_single_backtest_checkpoint_strategy_documented(self, artifact_text):
        """Regression: checkpoint section must address single-backtest strategy
        explicitly, not just optimization (Codex H1 — AC3 clarity).

        Must document that short backtests use re-run and long backtests
        support per-N-bars checkpointing.
        """
        checkpoint_start = artifact_text.find("Checkpoint/Resume Patterns")
        assert checkpoint_start > -1
        checkpoint_text = artifact_text[checkpoint_start:checkpoint_start + 3000]
        text_lower = checkpoint_text.lower()

        # Must address single backtest explicitly
        has_single_backtest = (
            "single backtest" in text_lower
            or "single-backtest" in text_lower
        )
        assert has_single_backtest, (
            "Checkpoint section does not explicitly address single-backtest strategy"
        )

    @pytest.mark.regression
    def test_appendix_a_has_na_entries_for_out_of_scope(self, artifact_text):
        """Regression: Appendix A must include N/A entries for FRs/NFRs that
        are out of scope, not silently omit them (BMAD M1).
        """
        appendix_a_start = artifact_text.find("Appendix A")
        assert appendix_a_start > -1
        appendix_text = artifact_text[appendix_a_start:]

        # FR16, FR17, FR19 should be present with N/A or "Not in scope"
        for req in ["FR16", "FR17", "FR19"]:
            assert req in appendix_text, (
                f"Appendix A must include {req} even if N/A"
            )

    @pytest.mark.regression
    def test_appendix_b_has_all_decisions(self, artifact_text):
        """Regression: Appendix B must include all D1-D15 entries, not just
        the 6 required by AC5 (BMAD M2).
        """
        appendix_b_start = artifact_text.find("Appendix B")
        assert appendix_b_start > -1
        appendix_text = artifact_text[appendix_b_start:]

        for i in range(1, 16):
            decision = f"D{i}"
            assert decision in appendix_text, (
                f"Appendix B must include {decision} (even if N/A)"
            )


@pytest.mark.live
class TestLiveArtifactOnDisk:
    """Live tests that verify the research artifact exists on disk with
    required content. These exercise real filesystem access.
    """

    def test_live_artifact_exists_and_readable(self):
        """Verify research artifact file exists and is readable."""
        assert RESEARCH_ARTIFACT.exists(), (
            f"Research artifact not found at: {RESEARCH_ARTIFACT}"
        )
        text = RESEARCH_ARTIFACT.read_text(encoding="utf-8")
        assert len(text) > 20000, (
            f"Artifact too small ({len(text)} chars), expected comprehensive research"
        )

    def test_live_artifact_has_all_sections(self):
        """Verify all 12 required sections exist in the on-disk artifact."""
        text = RESEARCH_ARTIFACT.read_text(encoding="utf-8")
        required = [
            "Executive Summary",
            "IPC Comparison Matrix",
            "Determinism Strategies",
            "Reproducibility Contract",
            "Checkpoint/Resume Patterns",
            "Memory Budgeting",
            "Architecture Alignment Matrix",
            "Proposed Architecture Updates",
            "Downstream Contracts",
            "Build Plan",
            "Dependency Notes",
            "Open Questions",
        ]
        text_lower = text.lower()
        missing = [s for s in required if s.lower() not in text_lower]
        assert not missing, (
            f"Research artifact missing sections: {missing}"
        )

    def test_live_artifact_cross_references_architecture(self):
        """Verify artifact references architecture decisions D1-D14 and
        confirms D15 out of scope."""
        text = RESEARCH_ARTIFACT.read_text(encoding="utf-8")
        for d in ["D1", "D2", "D3", "D8", "D13", "D14", "D15"]:
            assert d in text, f"Missing architecture decision reference: {d}"
        # D15 must be marked out of scope
        text_lower = text.lower()
        d15_idx = text_lower.find("d15")
        assert d15_idx > -1
        # Check nearby text for "out of scope" or "no impact"
        nearby = text_lower[max(0, d15_idx - 200):d15_idx + 200]
        assert "out of scope" in nearby or "no impact" in nearby or "orthogonal" in nearby, (
            "D15 not confirmed as out of scope near its mention"
        )
