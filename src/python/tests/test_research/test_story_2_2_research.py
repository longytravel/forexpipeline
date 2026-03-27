"""Tests for Story 2.2: Strategy Definition Format & Cost Modeling Research.

This is a research story — no production code. Tests validate the research
artifact exists on disk, has required sections, contains required content,
and satisfies all 11 acceptance criteria.
"""

import json
import re
from pathlib import Path

import pytest

# Project root — file is at src/python/tests/test_research/test_story_2_2_research.py
PROJECT_ROOT = Path(__file__).resolve().parents[4]
RESEARCH_ARTIFACT = (
    PROJECT_ROOT
    / "_bmad-output"
    / "planning-artifacts"
    / "research"
    / "strategy-definition-format-cost-modeling-research.md"
)
STORY_FILE = (
    PROJECT_ROOT
    / "_bmad-output"
    / "implementation-artifacts"
    / "2-2-strategy-definition-format-cost-modeling-research.md"
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
    """Verify research artifact has all required sections."""

    REQUIRED_SECTIONS = [
        "Executive Summary",
        "Story 2.1 Findings Summary",
        "Strategy Definition Format Comparison",
        "Format Recommendation",
        "Constraint Validation Analysis",
        "Execution Cost Modeling Research",
        "Cost Model Artifact Assessment",
        "Proposed Architecture Updates",
        "Build Plan Confirmation",
        "Downstream Rewrite Risk",
    ]

    def test_artifact_exists(self):
        assert RESEARCH_ARTIFACT.exists()

    def test_artifact_not_empty(self, artifact_text):
        assert len(artifact_text) > 1000, "Artifact too short for research story"

    def test_artifact_within_size_limits(self, artifact_text):
        word_count = len(artifact_text.split())
        assert word_count <= 8000, (
            f"Artifact over-scoped: {word_count} words (limit 6000 target, 8000 hard)"
        )

    @pytest.mark.parametrize("section", REQUIRED_SECTIONS)
    def test_required_section_present(self, artifact_text, section):
        assert section.lower() in artifact_text.lower(), (
            f"Missing required section: {section}"
        )


class TestFormatResearch:
    """Verify format comparison meets AC#1, AC#3, AC#7."""

    def test_at_least_three_format_options(self, artifact_text):
        """AC#3: at least 3 format options evaluated."""
        options_found = 0
        for option in ["TOML", "JSON", "DSL", "Hybrid"]:
            if re.search(rf"Option [A-D].*{option}", artifact_text, re.IGNORECASE):
                options_found += 1
        assert options_found >= 3, (
            f"Only {options_found} format options found, need >= 3"
        )

    def test_comparison_matrix_exists(self, artifact_text):
        """AC#3: scored tradeoff matrix."""
        assert "Weighted Total" in artifact_text or "weighted" in artifact_text.lower()

    def test_five_criteria_evaluated(self, artifact_text):
        """AC#3: comparison covers all 5 criteria."""
        criteria = [
            "Rust parseability",
            "AI-generation suitability",
            "Expressiveness",
            "Operator reviewability",
            "Tooling availability",
        ]
        for criterion in criteria:
            assert criterion.lower() in artifact_text.lower(), (
                f"Missing criterion: {criterion}"
            )

    def test_format_recommendation_with_rationale(self, artifact_text):
        """AC#1: recommendation with rationale."""
        assert "Chosen" in artifact_text or "Recommend" in artifact_text
        assert "D10" in artifact_text, "Recommendation must cite D10"

    def test_constraint_validation_decision(self, artifact_text):
        """AC#7: constraint validation timing decided."""
        text_lower = artifact_text.lower()
        assert "definition-time" in text_lower or "definition time" in text_lower
        assert "runtime" in text_lower or "load-time" in text_lower


class TestCostModelResearch:
    """Verify cost model research meets AC#2, AC#5, AC#6, AC#11."""

    def test_broker_spread_sources(self, artifact_text):
        """AC#2: broker-published spread data sources."""
        sources = ["Dukascopy", "OANDA"]
        for source in sources:
            assert source in artifact_text, f"Missing broker source: {source}"

    def test_session_aware_profiles(self, artifact_text):
        """AC#2, AC#5: session-aware cost profiles."""
        sessions = ["asian", "london", "new_york", "london_ny_overlap", "off_hours"]
        for session in sessions:
            assert session in artifact_text.lower(), (
                f"Missing session: {session}"
            )

    def test_slippage_research(self, artifact_text):
        """AC#2: slippage research methodology."""
        assert "slippage" in artifact_text.lower()
        assert "pip" in artifact_text.lower()

    def test_academic_citations(self, artifact_text):
        """AC#5: academic/published research cited."""
        # At least 2 citations
        citation_patterns = [
            r"\d{4}\)",  # (2020) style
            r"\d{4}\]",  # [2020] style
            r"\d{4}\:",  # 2020: style
            r"et al",
            r"BIS",
            r"NBER",
        ]
        citations_found = sum(
            1 for p in citation_patterns if re.search(p, artifact_text)
        )
        assert citations_found >= 2, "Insufficient academic citations"

    def test_mean_std_vs_quantiles_decision(self, artifact_text):
        """AC#11: explicit decision on mean/std vs percentiles."""
        text_lower = artifact_text.lower()
        assert "p95" in text_lower or "percentile" in text_lower
        assert "mean" in text_lower and "std" in text_lower

    def test_quarantine_interaction_addressed(self, artifact_text):
        """Critical: quarantine interaction with cost model documented."""
        text_lower = artifact_text.lower()
        assert "quarantine" in text_lower
        assert "pre-quarantine" in text_lower or "raw data" in text_lower

    def test_cost_model_schema_example(self, artifact_text):
        """AC#2: cost model artifact structure with example."""
        assert "mean_spread_pips" in artifact_text
        assert "std_spread" in artifact_text
        assert "mean_slippage_pips" in artifact_text

    def test_commission_field_addressed(self, artifact_text):
        """Cost model must address commission (ECN brokers)."""
        assert "commission" in artifact_text.lower()

    def test_data_provenance_documented(self, artifact_text):
        """AC#2: data provenance requirements."""
        text_lower = artifact_text.lower()
        assert "data_source" in text_lower or "provenance" in text_lower
        assert "ecn" in text_lower or "market maker" in text_lower


class TestArchitectureAlignment:
    """Verify architecture alignment meets AC#4, AC#8."""

    REQUIRED_DECISIONS = ["D10", "D13", "D14"]

    @pytest.mark.parametrize("decision", REQUIRED_DECISIONS)
    def test_architecture_decision_referenced(self, artifact_text, decision):
        """AC#4: alignment with architecture decisions."""
        assert decision in artifact_text, (
            f"Missing architecture decision reference: {decision}"
        )

    def test_prd_requirements_referenced(self, artifact_text):
        """AC#4: PRD requirements referenced."""
        for fr in ["FR9", "FR11", "FR12", "FR20", "FR21"]:
            assert fr in artifact_text, f"Missing PRD requirement: {fr}"

    def test_architecture_changes_in_artifact_only(self, artifact_text):
        """AC#8: proposed changes documented in artifact, not architecture.md."""
        assert "Proposed Architecture Updates" in artifact_text
        # Verify the section says changes stay in artifact
        assert "NOT" in artifact_text or "not modified" in artifact_text.lower() or "no change" in artifact_text.lower()


class TestDecisionRecords:
    """Verify decision records meet AC#10."""

    def test_format_decision_record_complete(self, artifact_text):
        """AC#10: decision record for format recommendation."""
        text_lower = artifact_text.lower()
        assert "chosen" in text_lower
        assert "rejected" in text_lower
        assert "evidence" in text_lower or "rationale" in text_lower

    def test_rejected_options_with_reasons(self, artifact_text):
        """AC#10: rejected options documented with reasons."""
        assert "Rejection Reason" in artifact_text or "Reason for Rejection" in artifact_text


class TestBuildPlan:
    """Verify build plan meets AC#9."""

    DOWNSTREAM_STORIES = ["2.3", "2.4", "2.5", "2.6", "2.7", "2.8", "2.9"]

    def test_build_plan_covers_all_stories(self, artifact_text):
        """AC#9: build plan for Stories 2.3-2.9."""
        for story in self.DOWNSTREAM_STORIES:
            assert story in artifact_text, (
                f"Missing build plan for Story {story}"
            )

    def test_port_vs_build_classification(self, artifact_text):
        """AC#9: per-story port vs build classification."""
        text_lower = artifact_text.lower()
        assert "build new" in text_lower or "port" in text_lower


class TestStoryCompletion:
    """Verify story file is properly completed."""

    def test_all_tasks_checked(self, story_text):
        """All tasks and subtasks must be marked [x]."""
        unchecked = re.findall(r"- \[ \]", story_text)
        assert len(unchecked) == 0, (
            f"Found {len(unchecked)} unchecked tasks in story file"
        )

    def test_status_is_review(self, story_text):
        """Story status should be 'review'."""
        assert "Status: review" in story_text

    def test_dev_agent_record_populated(self, story_text):
        """Dev Agent Record must have completion notes."""
        assert "Completion Notes" in story_text
        # Should have actual content after the heading
        idx = story_text.index("Completion Notes List")
        after = story_text[idx : idx + 500]
        assert "Task 1" in after or "TOML" in after

    def test_file_list_populated(self, story_text):
        """File List must list changed files."""
        idx = story_text.index("### File List")
        after = story_text[idx : idx + 500]
        assert "strategy-definition-format-cost-modeling-research.md" in after


# ---------------------------------------------------------------------------
# Live tests — verify real artifact on disk
# ---------------------------------------------------------------------------


@pytest.mark.live
class TestLiveResearchArtifactExists:
    """Live test: verify the research artifact exists on disk and is valid."""

    def test_live_artifact_exists_on_disk(self):
        """The research artifact file must exist at the expected path."""
        assert RESEARCH_ARTIFACT.exists(), (
            f"Research artifact missing: {RESEARCH_ARTIFACT}"
        )
        size = RESEARCH_ARTIFACT.stat().st_size
        assert size > 5000, f"Artifact suspiciously small: {size} bytes"

    def test_live_artifact_readable_utf8(self):
        """Artifact must be valid UTF-8 markdown."""
        text = RESEARCH_ARTIFACT.read_text(encoding="utf-8")
        assert text.startswith("#"), "Artifact should start with markdown heading"

    def test_live_artifact_has_toml_examples(self):
        """Artifact must contain concrete TOML strategy spec examples."""
        text = RESEARCH_ARTIFACT.read_text(encoding="utf-8")
        assert "```toml" in text, "No TOML code blocks found in artifact"
        assert "[metadata]" in text, "No TOML metadata section example"
        assert "[[entry_rules]]" in text, "No TOML entry_rules example"

    def test_live_artifact_has_json_schema_example(self):
        """Artifact must contain cost model JSON schema example."""
        text = RESEARCH_ARTIFACT.read_text(encoding="utf-8")
        assert "```json" in text, "No JSON code blocks found in artifact"
        assert '"sessions"' in text, "No sessions field in JSON example"
        assert '"mean_spread_pips"' in text, "No mean_spread_pips in JSON example"

    def test_live_story_file_complete(self):
        """Story file must have all tasks checked and status=review."""
        text = STORY_FILE.read_text(encoding="utf-8")
        unchecked = re.findall(r"- \[ \]", text)
        assert len(unchecked) == 0, (
            f"{len(unchecked)} unchecked tasks remain"
        )
        assert "Status: review" in text

    def test_live_cost_model_v1_schema_complete(self):
        """The V1 cost model schema must include all required fields."""
        text = RESEARCH_ARTIFACT.read_text(encoding="utf-8")
        required_fields = [
            "mean_spread_pips",
            "std_spread",
            "median_spread_pips",
            "mean_slippage_pips",
            "std_slippage",
            "sample_count",
            "commission_per_lot_usd",
            "pip_value",
            "data_source",
            "schema_version",
        ]
        for field in required_fields:
            assert field in text, (
                f"V1 cost model schema missing field: {field}"
            )

    def test_live_all_eleven_acs_addressed(self):
        """All 11 acceptance criteria must be addressable from artifact content."""
        text = RESEARCH_ARTIFACT.read_text(encoding="utf-8")
        text_lower = text.lower()

        # AC1: format research artifact produced
        assert "strategy definition format" in text_lower

        # AC2: cost modeling research covers required topics
        assert "broker" in text_lower and "spread" in text_lower

        # AC3: 3+ format options with comparison
        assert "toml" in text_lower and "json" in text_lower and "dsl" in text_lower

        # AC4: architecture alignment
        assert "d10" in text_lower and "d13" in text_lower and "d14" in text_lower

        # AC5: session-aware with market microstructure
        assert "microstructure" in text_lower or "bid-ask" in text_lower

        # AC6: compared with D13
        assert "d13" in text_lower and "alignment" in text_lower

        # AC7: constraint validation timing
        assert "definition-time" in text_lower or "definition time" in text_lower

        # AC8: proposed refinements in artifact only
        assert "proposed architecture" in text_lower

        # AC9: build plan for 2.3-2.9
        assert "build plan" in text_lower

        # AC10: decision records
        assert "chosen" in text_lower and "rejected" in text_lower

        # AC11: mean/std vs quantiles decision
        assert "p95" in text_lower or "percentile" in text_lower


# ---------------------------------------------------------------------------
# Regression tests — catch specific bugs found in review synthesis
# ---------------------------------------------------------------------------


@pytest.mark.regression
class TestWeightedMatrixArithmetic:
    """Regression: Codex review found incorrect weighted totals in comparison matrix.

    The matrix weights are: Rust parseability 25%, AI-generation 25%,
    Expressiveness 20%, Operator reviewability 15%, Tooling 15%.
    Scores must multiply correctly.
    """

    WEIGHTS = [0.25, 0.25, 0.20, 0.15, 0.15]

    def _extract_matrix_row(self, artifact_text: str, option: str) -> list[int] | None:
        """Extract raw scores from the comparison matrix for a given option."""
        for line in artifact_text.splitlines():
            if f"| {option}" in line or f"|{option}" in line:
                # Skip header/separator lines
                cells = [c.strip() for c in line.split("|") if c.strip()]
                if len(cells) >= 7:  # Criterion, Weight, TOML, JSON, DSL, Hybrid
                    continue
        # Parse the matrix rows for individual criteria scores
        scores: dict[str, list[int]] = {"TOML": [], "JSON": [], "DSL": []}
        criteria_lines = []
        in_matrix = False
        for line in artifact_text.splitlines():
            if "Rust parseability" in line and "|" in line:
                in_matrix = True
            if in_matrix and line.startswith("|") and "---" not in line:
                cells = [c.strip() for c in line.split("|") if c.strip()]
                if len(cells) >= 5 and cells[0] not in ("Criterion", "**Weighted Total**"):
                    try:
                        # cells: criterion, weight, TOML, JSON, DSL, Hybrid
                        toml_score = int(cells[2].replace("**", ""))
                        json_score = int(cells[3].replace("**", ""))
                        dsl_score = int(cells[4])
                        scores["TOML"].append(toml_score)
                        scores["JSON"].append(json_score)
                        scores["DSL"].append(dsl_score)
                    except (ValueError, IndexError):
                        pass
            if in_matrix and "Weighted Total" in line:
                in_matrix = False
        return scores

    def _compute_weighted_total(self, raw_scores: list[int]) -> float:
        assert len(raw_scores) == len(self.WEIGHTS), (
            f"Expected {len(self.WEIGHTS)} scores, got {len(raw_scores)}"
        )
        return round(sum(s * w for s, w in zip(raw_scores, self.WEIGHTS)), 2)

    def _extract_stated_total(self, artifact_text: str, option: str) -> float | None:
        """Extract the stated weighted total from the matrix."""
        for line in artifact_text.splitlines():
            if "Weighted Total" in line and "|" in line:
                cells = [c.strip().replace("**", "") for c in line.split("|") if c.strip()]
                idx = {"TOML": 2, "JSON": 3, "DSL": 4}.get(option)
                if idx is not None and len(cells) > idx:
                    try:
                        return float(cells[idx])
                    except ValueError:
                        return None
        return None

    def test_toml_weighted_total_correct(self, artifact_text):
        """TOML weighted total must match individual scores × weights."""
        scores = self._extract_matrix_row(artifact_text, "TOML")
        assert scores and len(scores["TOML"]) == 5, "Could not extract 5 TOML scores"
        computed = self._compute_weighted_total(scores["TOML"])
        stated = self._extract_stated_total(artifact_text, "TOML")
        assert stated is not None, "Could not find stated TOML total"
        assert abs(computed - stated) < 0.01, (
            f"TOML total mismatch: computed {computed}, stated {stated}"
        )

    def test_json_weighted_total_correct(self, artifact_text):
        """JSON weighted total must match individual scores × weights."""
        scores = self._extract_matrix_row(artifact_text, "JSON")
        assert scores and len(scores["JSON"]) == 5, "Could not extract 5 JSON scores"
        computed = self._compute_weighted_total(scores["JSON"])
        stated = self._extract_stated_total(artifact_text, "JSON")
        assert stated is not None, "Could not find stated JSON total"
        assert abs(computed - stated) < 0.01, (
            f"JSON total mismatch: computed {computed}, stated {stated}"
        )

    def test_dsl_weighted_total_correct(self, artifact_text):
        """DSL weighted total must match individual scores × weights."""
        scores = self._extract_matrix_row(artifact_text, "DSL")
        assert scores and len(scores["DSL"]) == 5, "Could not extract 5 DSL scores"
        computed = self._compute_weighted_total(scores["DSL"])
        stated = self._extract_stated_total(artifact_text, "DSL")
        assert stated is not None, "Could not find stated DSL total"
        assert abs(computed - stated) < 0.01, (
            f"DSL total mismatch: computed {computed}, stated {stated}"
        )


@pytest.mark.regression
class TestCommissionArithmetic:
    """Regression: Codex review found commission undercounted by half.

    $3.50/side/lot means round-trip = $7.00/lot = 0.70 pips (at $10/pip).
    The annual cost example must reflect this.
    """

    def test_commission_per_side_is_round_trip_in_example(self, artifact_text):
        """Commission equivalent in cost example must be >= 0.70 pips (round-trip)."""
        # Find the commission equivalent value in the annual cost example
        match = re.search(
            r"(\d+\.\d+)\s*(?:pips?)?\s*(?:commission|commission equivalent)",
            artifact_text,
            re.IGNORECASE,
        )
        # Fall back: look for "spread + slippage + commission" pattern
        if not match:
            match = re.search(
                r"\+\s*(\d+\.\d+)\s+commission",
                artifact_text,
                re.IGNORECASE,
            )
        assert match, "Could not find commission equivalent in cost example"
        commission_pips = float(match.group(1))
        assert commission_pips >= 0.70, (
            f"Commission equivalent {commission_pips} pips is less than "
            f"round-trip minimum 0.70 pips ($3.50/side × 2)"
        )

    def test_annual_cost_omission_consistent(self, artifact_text):
        """Annual pip omission must be >= 500 trades × 1.80 pips = 900."""
        match = re.search(r"Annual omission:\s*~?(\d+)\s*pips", artifact_text)
        assert match, "Could not find annual omission figure"
        annual_pips = int(match.group(1))
        assert annual_pips >= 900, (
            f"Annual omission {annual_pips} pips is less than "
            f"expected 900 (500 trades × 1.80 pips/trade)"
        )


@pytest.mark.regression
class TestDecisionRecordCompleteness:
    """Regression: Both BMAD and Codex found AC#10 gaps in Sections 5 and 7.3.

    Each decision record must include: chosen option, rejected options,
    evidence sources, unresolved assumptions, downstream contract impact,
    and known limitations.
    """

    REQUIRED_ELEMENTS = [
        "chosen",
        "rejected",
        "evidence source",
        "unresolved assumption",
        "downstream contract impact",
        "known limitation",
    ]

    def _find_section(self, text: str, heading: str) -> str:
        """Extract text from a given ## heading to the next ## heading."""
        pattern = rf"(## \d*\.?\s*{re.escape(heading)}.*?)(?=\n## |\Z)"
        match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
        return match.group(1) if match else ""

    def test_section5_constraint_validation_has_all_elements(self, artifact_text):
        """Section 5 (Constraint Validation) decision record must be complete."""
        section = self._find_section(artifact_text, "Constraint Validation")
        assert section, "Section 5 (Constraint Validation) not found"
        section_lower = section.lower()
        for element in self.REQUIRED_ELEMENTS:
            assert element in section_lower, (
                f"Section 5 missing decision record element: '{element}'"
            )

    def test_section73_cost_model_decision_has_all_elements(self, artifact_text):
        """Section 7.3 (Mean/Std vs Quantiles) decision record must be complete."""
        # Section 7.3 is within Section 7, find by sub-heading
        pattern = r"(### 7\.3.*?)(?=\n### |\n## |\Z)"
        match = re.search(pattern, artifact_text, re.DOTALL)
        assert match, "Section 7.3 not found"
        section_lower = match.group(1).lower()
        for element in self.REQUIRED_ELEMENTS:
            assert element in section_lower, (
                f"Section 7.3 missing decision record element: '{element}'"
            )
