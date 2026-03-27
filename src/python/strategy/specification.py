"""Strategy Specification Pydantic v2 Models (D10, FR12).

Defines the specification layer of the three-layer strategy execution model:
intent -> specification -> evaluator.

A specification is structured data (not code) that the Rust evaluator interprets.
Validation is fail-loud: invalid specs raise ValidationError immediately.
"""

from __future__ import annotations

import re
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


# --- Version pattern ---
VERSION_PATTERN = re.compile(r"^v\d{3,}$")

# --- Enums as Literals (Pydantic v2 strict mode) ---
PairType = Literal["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "USDCHF", "NZDUSD", "XAUUSD"]
TimeframeType = Literal["M1", "M5", "M15", "H1", "H4", "D1"]
ComparatorType = Literal[">", "<", "==", ">=", "<=", "crosses_above", "crosses_below"]
StopLossType = Literal["fixed_pips", "atr_multiple", "percentage"]
TakeProfitType = Literal["fixed_pips", "atr_multiple", "percentage", "risk_reward"]
TrailingType = Literal["trailing_stop", "chandelier"]
SizingMethod = Literal["fixed_risk", "fixed_lots"]
FilterType = Literal["session", "volatility", "day_of_week"]
ObjectiveFunction = Literal["sharpe", "calmar", "profit_factor", "expectancy"]
SessionName = Literal["asian", "london", "new_york", "london_ny_overlap", "off_hours"]


class StrategyMetadata(BaseModel):
    """Strategy identity and versioning metadata."""

    model_config = ConfigDict(strict=True, extra="forbid")

    schema_version: str = Field(default="1", description="Schema version")
    name: str = Field(..., min_length=1, description="Strategy name")
    version: str = Field(..., description="Spec version (v001, v002, ...)")
    pair: PairType = Field(..., description="Trading pair")
    timeframe: TimeframeType = Field(..., description="Primary timeframe")
    created_by: str = Field(..., min_length=1, description="Creator agent/operator")
    status: Optional[str] = Field(
        default=None, description="Spec lifecycle status (draft/confirmed/locked)"
    )
    created_at: Optional[str] = Field(
        default=None, description="UTC ISO 8601 creation timestamp"
    )
    confirmed_at: Optional[str] = Field(
        default=None, description="UTC ISO 8601 confirmation timestamp (populated by Story 2.5)"
    )
    config_hash: Optional[str] = Field(
        default=None, description="Pipeline config hash (populated by Story 2.5)"
    )

    @field_validator("version")
    @classmethod
    def validate_version(cls, v: str) -> str:
        if not VERSION_PATTERN.match(v):
            raise ValueError(f"version must match pattern vNNN+ (e.g., v001, v1000), got '{v}'")
        return v


class EntryCondition(BaseModel):
    """Single entry condition based on an indicator."""

    model_config = ConfigDict(strict=True, extra="forbid")

    indicator: str = Field(..., min_length=1, description="Indicator type from registry")
    parameters: dict[str, int | float | str] = Field(
        ..., description="Indicator-specific parameters"
    )
    threshold: float = Field(..., description="Comparison threshold")
    comparator: ComparatorType = Field(..., description="Comparison operator")


class EntryFilter(BaseModel):
    """Pre-entry filter (session, volatility, or day_of_week)."""

    model_config = ConfigDict(strict=True, extra="forbid")

    type: FilterType = Field(..., description="Filter type discriminator")
    params: dict[str, list[str] | list[int] | str | int | float] = Field(
        ..., description="Filter-type-specific parameters"
    )

    @model_validator(mode="after")
    def validate_filter_params(self) -> EntryFilter:
        """Validate filter params match the declared filter type."""
        if self.type == "session":
            include = self.params.get("include")
            if not include or not isinstance(include, list):
                raise ValueError(
                    "session filter requires 'include' param with list of session names"
                )
            valid_sessions = {"asian", "london", "new_york", "london_ny_overlap", "off_hours"}
            for s in include:
                if s not in valid_sessions:
                    raise ValueError(
                        f"Invalid session '{s}'. Valid: {sorted(valid_sessions)}"
                    )
        elif self.type == "volatility":
            if "indicator" not in self.params:
                raise ValueError("volatility filter requires 'indicator' param")
            if "period" not in self.params:
                raise ValueError("volatility filter requires 'period' param")
            period = self.params.get("period")
            if isinstance(period, (int, float)) and period <= 0:
                raise ValueError("volatility filter 'period' must be > 0")
        elif self.type == "day_of_week":
            include = self.params.get("include")
            if not include or not isinstance(include, list):
                raise ValueError(
                    "day_of_week filter requires 'include' param with list of day numbers"
                )
            for d in include:
                if not isinstance(d, int) or d < 0 or d > 6:
                    raise ValueError(
                        f"Invalid day_of_week '{d}'. Must be int 0-6 (0=Monday)"
                    )
        return self


class EntryConfirmation(BaseModel):
    """Optional confirmation condition (same structure as EntryCondition)."""

    model_config = ConfigDict(strict=True, extra="forbid")

    indicator: str = Field(..., min_length=1, description="Confirmation indicator")
    parameters: dict[str, int | float | str] = Field(
        ..., description="Indicator-specific parameters"
    )
    threshold: float = Field(..., description="Comparison threshold")
    comparator: ComparatorType = Field(..., description="Comparison operator")


class EntryRules(BaseModel):
    """Entry signal rules: conditions, filters, and optional confirmations."""

    model_config = ConfigDict(strict=True, extra="forbid")

    conditions: list[EntryCondition] = Field(
        ..., min_length=1, description="Entry conditions (all must be true)"
    )
    filters: list[EntryFilter] = Field(
        default_factory=list, description="Pre-entry filters"
    )
    confirmation: list[EntryConfirmation] = Field(
        default_factory=list, description="Optional confirmations"
    )


class ExitStopLoss(BaseModel):
    """Stop loss configuration."""

    model_config = ConfigDict(strict=True, extra="forbid")

    type: StopLossType = Field(..., description="Stop loss calculation method")
    value: float = Field(..., gt=0, description="Stop loss value")


class ExitTakeProfit(BaseModel):
    """Take profit configuration."""

    model_config = ConfigDict(strict=True, extra="forbid")

    type: TakeProfitType = Field(..., description="Take profit calculation method")
    value: float = Field(..., gt=0, description="Take profit value")


class ExitTrailing(BaseModel):
    """Trailing stop configuration."""

    model_config = ConfigDict(strict=True, extra="forbid")

    type: TrailingType = Field(..., description="Trailing stop type")
    params: dict[str, int | float] = Field(
        ..., description="Type-specific trailing parameters"
    )

    @model_validator(mode="after")
    def validate_trailing_params(self) -> ExitTrailing:
        """Validate trailing params match the declared type."""
        if self.type == "trailing_stop":
            if "distance_pips" not in self.params:
                raise ValueError("trailing_stop requires 'distance_pips' param")
            distance = self.params.get("distance_pips")
            if isinstance(distance, (int, float)) and distance <= 0:
                raise ValueError("trailing_stop 'distance_pips' must be > 0")
        elif self.type == "chandelier":
            if "atr_period" not in self.params:
                raise ValueError("chandelier requires 'atr_period' param")
            if "atr_multiplier" not in self.params:
                raise ValueError("chandelier requires 'atr_multiplier' param")
            atr_period = self.params.get("atr_period")
            if isinstance(atr_period, (int, float)) and atr_period <= 0:
                raise ValueError("chandelier 'atr_period' must be > 0")
            atr_mult = self.params.get("atr_multiplier")
            if isinstance(atr_mult, (int, float)) and atr_mult <= 0:
                raise ValueError("chandelier 'atr_multiplier' must be > 0")
        return self


class ExitRules(BaseModel):
    """Exit rule definitions."""

    model_config = ConfigDict(strict=True, extra="forbid")

    stop_loss: ExitStopLoss = Field(..., description="Stop loss config")
    take_profit: ExitTakeProfit = Field(..., description="Take profit config")
    trailing: Optional[ExitTrailing] = Field(
        default=None, description="Optional trailing stop"
    )


class PositionSizing(BaseModel):
    """Position sizing method and constraints (FR12)."""

    model_config = ConfigDict(strict=True, extra="forbid")

    method: SizingMethod = Field(..., description="Sizing method")
    risk_percent: float = Field(
        ..., ge=0.1, le=10.0, description="Risk per trade percentage"
    )
    max_lots: float = Field(
        ..., ge=0.01, le=100.0, description="Maximum lot size cap"
    )
    min_lots: float = Field(
        default=0.01, ge=0.01, le=100.0, description="Minimum lot size"
    )
    lot_step: float = Field(
        default=0.01, gt=0, description="Lot size increment"
    )


AccountCurrency = Literal["USD", "GBP", "EUR", "JPY", "AUD", "CAD", "CHF", "NZD"]


class AccountConfig(BaseModel):
    """Backtest account configuration."""

    model_config = ConfigDict(strict=True, extra="forbid")

    starting_balance: float = Field(..., gt=0, description="Starting account balance")
    currency: AccountCurrency = Field(..., description="Account denomination currency")
    leverage: int = Field(default=100, ge=1, le=500, description="Account leverage")


class SchemaVersionError(ValueError):
    """Raised when a legacy v1 optimization_plan format is encountered."""


ParameterType = Literal["continuous", "integer", "categorical"]


class ParameterCondition(BaseModel):
    """Conditional activation rule linking a parameter to a parent categorical choice."""

    model_config = ConfigDict(strict=True, extra="forbid")

    parent: str = Field(..., min_length=1, description="Parent categorical parameter name")
    value: str = Field(..., min_length=1, description="Parent value that activates this parameter")


class SearchParameter(BaseModel):
    """Single searchable parameter in the optimization space (D10 taxonomy)."""

    model_config = ConfigDict(strict=True, extra="forbid")

    type: ParameterType
    min: Optional[float] = None
    max: Optional[float] = None
    step: Optional[float] = None
    choices: Optional[list[str]] = None
    condition: Optional[ParameterCondition] = None

    @model_validator(mode="after")
    def validate_parameter(self) -> SearchParameter:
        """Validate fields based on parameter type."""
        if self.type in ("continuous", "integer"):
            if self.min is None or self.max is None:
                raise ValueError(
                    f"{self.type} parameter requires both min and max"
                )
            if self.min >= self.max:
                raise ValueError(
                    f"min ({self.min}) must be less than max ({self.max})"
                )
            if self.step is not None and self.step <= 0:
                raise ValueError(f"step must be > 0, got {self.step}")
            if self.choices is not None:
                raise ValueError(f"{self.type} parameter must not have choices")
            if self.type == "integer":
                if self.min != int(self.min):
                    raise ValueError(
                        f"integer parameter min must be a whole number, got {self.min}"
                    )
                if self.max != int(self.max):
                    raise ValueError(
                        f"integer parameter max must be a whole number, got {self.max}"
                    )
        elif self.type == "categorical":
            if self.choices is None or len(self.choices) < 2:
                raise ValueError(
                    "categorical parameter requires choices with at least 2 entries"
                )
            if self.min is not None or self.max is not None or self.step is not None:
                raise ValueError(
                    "categorical parameter must not have min/max/step"
                )
        return self


class OptimizationPlan(BaseModel):
    """Flat parameter optimization configuration (FR24, D10 taxonomy).

    Replaces the legacy staged parameter_groups format with a flat
    registry of searchable parameters. Each parameter declares its type,
    bounds, and optional conditional activation.
    """

    model_config = ConfigDict(strict=True, extra="forbid")

    schema_version: Literal[2] = Field(
        ..., description="Must be 2 for flat parameter format"
    )
    parameters: dict[str, SearchParameter] = Field(
        ..., min_length=1, description="Flat registry of searchable parameters"
    )
    objective_function: ObjectiveFunction = Field(
        ..., description="Optimization objective"
    )
    year_range: list[int] | None = Field(
        default=None, description="Optional [start_year, end_year] to filter data"
    )
    prescreening: dict | None = Field(
        default=None, description="Optional pre-screening config (enabled, mode, etc.)"
    )

    @model_validator(mode="after")
    def validate_condition_dag(self) -> OptimizationPlan:
        """Validate condition references and detect cycles in the condition DAG."""
        for param_name, param in self.parameters.items():
            if param.condition is None:
                continue
            parent_name = param.condition.parent
            if parent_name not in self.parameters:
                raise ValueError(
                    f"Parameter '{param_name}' condition references unknown "
                    f"parent '{parent_name}'"
                )
            parent = self.parameters[parent_name]
            if parent.type != "categorical":
                raise ValueError(
                    f"Parameter '{param_name}' condition parent '{parent_name}' "
                    f"must be categorical, got {parent.type}"
                )
            if param.condition.value not in parent.choices:
                raise ValueError(
                    f"Parameter '{param_name}' condition value "
                    f"'{param.condition.value}' not in parent '{parent_name}' "
                    f"choices: {parent.choices}"
                )

        # Cycle detection via DFS
        adj: dict[str, list[str]] = {name: [] for name in self.parameters}
        for param_name, param in self.parameters.items():
            if param.condition is not None:
                adj[param.condition.parent].append(param_name)

        WHITE, GRAY, BLACK = 0, 1, 2
        color: dict[str, int] = {name: WHITE for name in self.parameters}

        def dfs(node: str) -> bool:
            color[node] = GRAY
            for neighbor in adj[node]:
                if color[neighbor] == GRAY:
                    return True  # cycle
                if color[neighbor] == WHITE and dfs(neighbor):
                    return True
            color[node] = BLACK
            return False

        for node in self.parameters:
            if color[node] == WHITE:
                if dfs(node):
                    raise ValueError(
                        "Circular dependency detected in parameter conditions"
                    )

        return self


class CostModelReference(BaseModel):
    """Reference to versioned cost model artifact (D13)."""

    model_config = ConfigDict(strict=True, extra="forbid")

    version: str = Field(..., description="Cost model version (e.g., v001)")

    @field_validator("version")
    @classmethod
    def validate_version(cls, v: str) -> str:
        if not VERSION_PATTERN.match(v):
            raise ValueError(
                f"cost_model_reference version must match pattern vNNN, got '{v}'"
            )
        return v


class StrategySpecification(BaseModel):
    """Top-level strategy specification (D10 specification layer).

    A versioned, deterministic, constrained strategy definition as structured data.
    The Rust evaluator interprets this — it is NOT code.
    """

    model_config = ConfigDict(strict=True, extra="forbid")

    metadata: StrategyMetadata
    entry_rules: EntryRules
    exit_rules: ExitRules
    position_sizing: PositionSizing
    account: Optional[AccountConfig] = Field(
        default=None, description="Backtest account configuration"
    )
    optimization_plan: Optional[OptimizationPlan] = Field(
        default=None, description="Optimization config (set during Story 2.8 setup)"
    )
    cost_model_reference: Optional[CostModelReference] = Field(
        default=None, description="Cost model ref (set during Story 2.6)"
    )
