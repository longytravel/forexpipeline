//! Backtest metrics computation (AC #7).
//!
//! Computes: win rate, profit factor, Sharpe ratio (unannualized),
//! R-squared, max drawdown (amount, pct, duration), total trades, avg duration.

use crate::trade_simulator::TradeRecord;
use serde::Deserialize;

/// Score computation mode for optimization.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum ScoreMode {
    /// Sharpe ratio only (legacy).
    Sharpe,
    /// Weighted composite of Sharpe, R², PF, DD, trades, win rate.
    #[default]
    Composite,
}

impl ScoreMode {
    pub fn from_str_opt(s: Option<&str>) -> Self {
        match s {
            Some("sharpe") => ScoreMode::Sharpe,
            _ => ScoreMode::Composite,
        }
    }
}

/// Weights for composite scoring, normalised to [0, 1] per component.
/// Default weights from research: Sharpe 0.25, R² 0.25, PF 0.15, DD 0.15,
/// trade count 0.10, win rate 0.10.
pub const COMPOSITE_W_SHARPE: f64 = 0.25;
pub const COMPOSITE_W_R2: f64 = 0.25;
pub const COMPOSITE_W_PF: f64 = 0.15;
pub const COMPOSITE_W_DD: f64 = 0.15;
pub const COMPOSITE_W_TRADES: f64 = 0.10;
pub const COMPOSITE_W_WINRATE: f64 = 0.10;

/// Compute composite quality score from individual metrics.
///
/// Hard profitability gate: candidates with Sharpe <= 0 score 0.
/// Among profitable candidates, each component is normalised to [0.0, 1.0]
/// using calibrated thresholds, then weighted and summed.
///
/// Data-driven calibration (10,185 candidates, gen_000000 wide-22yr):
/// - Hard gate ensures 100% of top-ranked candidates are profitable
/// - Spearman rho=0.66 among profitable: composite adds meaningful
///   differentiation by rewarding robustness (R², PF, low DD)
/// - Best score spread (0.118 std) for optimizer gradient signal
pub fn compute_composite_score(
    sharpe: f64,
    r_squared: f64,
    profit_factor: f64,
    max_dd_pct: f64,
    trade_count: u32,
    win_rate: f64,
) -> f64 {
    // Hard gate: unprofitable strategies score 0
    if sharpe <= 0.0 {
        return 0.0;
    }

    // Normalise each component to [0, 1]
    let s_sharpe = clamp01(sharpe / 3.0);                               // [0, 3] -> [0, 1]
    let s_r2 = clamp01(r_squared);                                      // already [0, 1]
    let s_pf = clamp01(profit_factor / 5.0);                            // [0, 5] -> [0, 1]
    let s_dd = clamp01(1.0 - (max_dd_pct / 50.0));                     // 0%=1.0, 50%=0.0 (inverted)
    let s_trades = clamp01((trade_count as f64 - 30.0) / (200.0 - 30.0)); // [30, 200] -> [0, 1]
    let s_wr = clamp01(win_rate);                                       // already [0, 1]

    COMPOSITE_W_SHARPE * s_sharpe
        + COMPOSITE_W_R2 * s_r2
        + COMPOSITE_W_PF * s_pf
        + COMPOSITE_W_DD * s_dd
        + COMPOSITE_W_TRADES * s_trades
        + COMPOSITE_W_WINRATE * s_wr
}

#[inline]
fn clamp01(v: f64) -> f64 {
    v.max(0.0).min(1.0)
}

/// Summary metrics for a completed backtest.
#[derive(Debug, Clone)]
pub struct Metrics {
    pub win_rate: f64,
    pub profit_factor: f64,
    pub sharpe_ratio: f64,
    pub r_squared: f64,
    pub max_drawdown_pips: f64,
    pub max_drawdown_pct: f64,
    pub max_drawdown_duration_bars: u64,
    pub total_trades: u64,
    pub avg_trade_duration_bars: f64,
    pub winning_trades: u64,
    pub losing_trades: u64,
    pub avg_win: f64,
    pub avg_loss: f64,
    pub largest_win: f64,
    pub largest_loss: f64,
    pub net_pnl_pips: f64,
    pub avg_trade_pips: f64,
}

/// Equity point for drawdown tracking.
#[derive(Debug)]
pub struct EquityPoint {
    pub bar_index: u64,
    pub equity: f64,
}

/// Compute all metrics from trade records and equity curve.
pub fn compute_metrics(
    trades: &[TradeRecord],
    equity_points: &[EquityPoint],
) -> Metrics {
    let total_trades = trades.len() as u64;

    // Zero-trades edge case: all metrics to 0.0
    if total_trades == 0 {
        return Metrics {
            win_rate: 0.0,
            profit_factor: 0.0,
            sharpe_ratio: 0.0,
            r_squared: 0.0,
            max_drawdown_pips: 0.0,
            max_drawdown_pct: 0.0,
            max_drawdown_duration_bars: 0,
            total_trades: 0,
            avg_trade_duration_bars: 0.0,
            winning_trades: 0,
            losing_trades: 0,
            avg_win: 0.0,
            avg_loss: 0.0,
            largest_win: 0.0,
            largest_loss: 0.0,
            net_pnl_pips: 0.0,
            avg_trade_pips: 0.0,
        };
    }

    let pnls: Vec<f64> = trades.iter().map(|t| t.pnl).collect();

    let winning_trades = pnls.iter().filter(|&&p| p > 0.0).count() as u64;
    let losing_trades = pnls.iter().filter(|&&p| p < 0.0).count() as u64;

    let win_rate = winning_trades as f64 / total_trades as f64;

    let sum_wins: f64 = pnls.iter().filter(|&&p| p > 0.0).sum();
    let sum_losses: f64 = pnls.iter().filter(|&&p| p < 0.0).map(|p| p.abs()).sum();

    let profit_factor = if sum_losses == 0.0 {
        if sum_wins > 0.0 { f64::MAX } else { 0.0 }
    } else {
        sum_wins / sum_losses
    };

    // Sharpe ratio: mean(pnl) / std(pnl), unannualized
    let mean_pnl = pnls.iter().sum::<f64>() / total_trades as f64;
    let sharpe_ratio = if total_trades < 2 {
        0.0
    } else {
        let variance = pnls.iter().map(|p| (p - mean_pnl).powi(2)).sum::<f64>()
            / (total_trades as f64 - 1.0);
        let std = variance.sqrt();
        if std == 0.0 { 0.0 } else { mean_pnl / std }
    };

    // Win/loss averages
    let avg_win = if winning_trades > 0 {
        sum_wins / winning_trades as f64
    } else {
        0.0
    };
    let avg_loss = if losing_trades > 0 {
        -sum_losses / losing_trades as f64
    } else {
        0.0
    };

    let largest_win = pnls.iter().cloned().fold(0.0_f64, f64::max);
    let largest_loss = pnls.iter().cloned().fold(0.0_f64, f64::min);

    let net_pnl_pips = pnls.iter().sum::<f64>();
    let avg_trade_pips = mean_pnl;

    // Avg trade duration
    let avg_trade_duration_bars = trades.iter().map(|t| t.holding_duration_bars as f64).sum::<f64>()
        / total_trades as f64;

    // R-squared: linear regression of equity curve
    let r_squared = compute_r_squared(equity_points);

    // Max drawdown from equity points
    let (dd_pips, dd_pct, dd_duration) = compute_max_drawdown(equity_points);

    Metrics {
        win_rate,
        profit_factor,
        sharpe_ratio,
        r_squared,
        max_drawdown_pips: dd_pips,
        max_drawdown_pct: dd_pct,
        max_drawdown_duration_bars: dd_duration,
        total_trades,
        avg_trade_duration_bars,
        winning_trades,
        losing_trades,
        avg_win,
        avg_loss,
        largest_win,
        largest_loss,
        net_pnl_pips,
        avg_trade_pips,
    }
}

/// R-squared of equity curve via linear regression (OLS).
fn compute_r_squared(points: &[EquityPoint]) -> f64 {
    let n = points.len() as f64;
    if n < 2.0 {
        return 0.0;
    }

    let xs: Vec<f64> = points.iter().map(|p| p.bar_index as f64).collect();
    let ys: Vec<f64> = points.iter().map(|p| p.equity).collect();

    let mean_x = xs.iter().sum::<f64>() / n;
    let mean_y = ys.iter().sum::<f64>() / n;

    let ss_xx: f64 = xs.iter().map(|x| (x - mean_x).powi(2)).sum();
    let ss_yy: f64 = ys.iter().map(|y| (y - mean_y).powi(2)).sum();
    let ss_xy: f64 = xs.iter().zip(ys.iter()).map(|(x, y)| (x - mean_x) * (y - mean_y)).sum();

    if ss_xx == 0.0 || ss_yy == 0.0 {
        return 0.0;
    }

    let r = ss_xy / (ss_xx * ss_yy).sqrt();
    r * r
}

/// Compute max drawdown from equity points.
/// Returns (max_dd_pips, max_dd_pct, max_dd_duration_bars).
///
/// Duration is measured as peak-to-recovery (or peak-to-end if no recovery),
/// per AC #7: "longest bar count between peak and recovery to new peak."
fn compute_max_drawdown(points: &[EquityPoint]) -> (f64, f64, u64) {
    if points.is_empty() {
        return (0.0, 0.0, 0);
    }

    let mut peak = points[0].equity;
    let mut peak_bar = points[0].bar_index;
    let mut max_dd_pips = 0.0_f64;
    let mut max_dd_pct = 0.0_f64;
    let mut max_dd_duration: u64 = 0;
    // Track current drawdown duration: bars since last peak
    let mut current_dd_start_bar = points[0].bar_index;
    let mut in_drawdown = false;

    for point in points {
        if point.equity >= peak {
            // New peak or recovery — record duration of completed drawdown
            if in_drawdown {
                let dd_duration = point.bar_index.saturating_sub(current_dd_start_bar);
                if dd_duration > max_dd_duration {
                    max_dd_duration = dd_duration;
                }
                in_drawdown = false;
            }
            peak = point.equity;
            peak_bar = point.bar_index;
            current_dd_start_bar = point.bar_index;
        } else {
            // In drawdown
            if !in_drawdown {
                in_drawdown = true;
                current_dd_start_bar = peak_bar;
            }
        }

        let dd_pips = peak - point.equity;
        let dd_pct = if peak > 0.0 {
            (dd_pips / peak) * 100.0
        } else {
            0.0
        };

        if dd_pips > max_dd_pips {
            max_dd_pips = dd_pips;
        }
        if dd_pct > max_dd_pct {
            max_dd_pct = dd_pct;
        }
    }

    // If still in drawdown at end of data, count bars from peak to end
    if in_drawdown {
        if let Some(last) = points.last() {
            let dd_duration = last.bar_index.saturating_sub(current_dd_start_bar);
            if dd_duration > max_dd_duration {
                max_dd_duration = dd_duration;
            }
        }
    }

    (max_dd_pips, max_dd_pct, max_dd_duration)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::position::{Direction, ExitReason};

    fn make_trade(pnl: f64, duration: u64) -> TradeRecord {
        TradeRecord {
            trade_id: 0,
            entry_time: 0,
            exit_time: 1000,
            entry_price_raw: 1.10000,
            entry_price: 1.10000,
            exit_price_raw: 1.10000,
            exit_price: 1.10000,
            entry_spread: 0.8,
            entry_slippage: 0.05,
            exit_spread: 0.8,
            exit_slippage: 0.05,
            direction: Direction::Long,
            entry_session: "london".to_string(),
            exit_session: "london".to_string(),
            signal_id: 0,
            pnl,
            holding_duration_bars: duration,
            exit_reason: ExitReason::TakeProfit,
            lot_size: 0.1,
        }
    }

    fn make_equity_points(values: &[(u64, f64)]) -> Vec<EquityPoint> {
        values.iter().map(|&(idx, eq)| EquityPoint { bar_index: idx, equity: eq }).collect()
    }

    #[test]
    fn test_win_rate_computation() {
        let trades = vec![
            make_trade(10.0, 5),
            make_trade(20.0, 3),
            make_trade(-5.0, 4),
            make_trade(15.0, 2),
        ];
        let eq = make_equity_points(&[(0, 0.0), (10, 45.0)]);
        let m = compute_metrics(&trades, &eq);
        assert!((m.win_rate - 0.75).abs() < 1e-10);
        assert_eq!(m.winning_trades, 3);
        assert_eq!(m.losing_trades, 1);
    }

    #[test]
    fn test_profit_factor_all_winners() {
        let trades = vec![make_trade(10.0, 5), make_trade(20.0, 3)];
        let eq = make_equity_points(&[(0, 0.0), (10, 30.0)]);
        let m = compute_metrics(&trades, &eq);
        assert_eq!(m.profit_factor, f64::MAX);
    }

    #[test]
    fn test_profit_factor_all_losers() {
        let trades = vec![make_trade(-10.0, 5), make_trade(-20.0, 3)];
        let eq = make_equity_points(&[(0, 0.0), (10, -30.0)]);
        let m = compute_metrics(&trades, &eq);
        assert!((m.profit_factor - 0.0).abs() < 1e-10);
    }

    #[test]
    fn test_sharpe_ratio_single_trade_returns_zero() {
        let trades = vec![make_trade(10.0, 5)];
        let eq = make_equity_points(&[(0, 0.0), (5, 10.0)]);
        let m = compute_metrics(&trades, &eq);
        assert!((m.sharpe_ratio - 0.0).abs() < 1e-10);
    }

    #[test]
    fn test_sharpe_ratio_normal() {
        let trades = vec![
            make_trade(10.0, 5),
            make_trade(20.0, 3),
            make_trade(-5.0, 4),
            make_trade(15.0, 2),
        ];
        let eq = make_equity_points(&[(0, 0.0), (14, 40.0)]);
        let m = compute_metrics(&trades, &eq);
        // mean = 10.0, std > 0 → sharpe > 0
        assert!(m.sharpe_ratio > 0.0);
    }

    #[test]
    fn test_r_squared_perfect_curve() {
        // Perfect linear equity curve → R² = 1.0
        let eq = make_equity_points(&[(0, 0.0), (1, 10.0), (2, 20.0), (3, 30.0), (4, 40.0)]);
        let r2 = super::compute_r_squared(&eq);
        assert!((r2 - 1.0).abs() < 1e-10, "Perfect linear should give R²=1.0, got {r2}");
    }

    #[test]
    fn test_max_drawdown_amount_and_duration() {
        // Equity: 0, 10, 20, 15, 10, 25, 30
        let eq = make_equity_points(&[
            (0, 0.0), (1, 10.0), (2, 20.0), (3, 15.0), (4, 10.0), (5, 25.0), (6, 30.0),
        ]);
        let (dd_pips, dd_pct, dd_dur) = super::compute_max_drawdown(&eq);
        // Max DD = 20 - 10 = 10 pips, pct = 10/20 * 100 = 50%
        // Duration: peak at bar 2, recovery at bar 5 (25 > 20) → 5-2=3 bars
        assert!((dd_pips - 10.0).abs() < 1e-10);
        assert!((dd_pct - 50.0).abs() < 1e-10);
        assert_eq!(dd_dur, 3);
    }

    #[test]
    fn test_breakeven_trades_not_counted_as_losses() {
        // Regression: breakeven (pnl == 0.0) trades must NOT be counted as losses.
        // They are neither winners nor losers.
        let trades = vec![
            make_trade(10.0, 5),  // winner
            make_trade(0.0, 3),   // breakeven — should NOT be a loss
            make_trade(-5.0, 4),  // loser
        ];
        let eq = make_equity_points(&[(0, 0.0), (12, 5.0)]);
        let m = compute_metrics(&trades, &eq);
        assert_eq!(m.total_trades, 3);
        assert_eq!(m.winning_trades, 1, "Only pnl > 0 are winners");
        assert_eq!(m.losing_trades, 1, "Only pnl < 0 are losers; breakeven excluded");
        // profit_factor should use only actual losses (not breakeven)
        assert!((m.profit_factor - (10.0 / 5.0)).abs() < 1e-10,
            "Profit factor should be 10/5 = 2.0, got {}", m.profit_factor);
    }

    #[test]
    fn test_zero_trades_returns_zero_metrics() {
        let trades: Vec<TradeRecord> = vec![];
        let eq: Vec<EquityPoint> = vec![];
        let m = compute_metrics(&trades, &eq);
        assert_eq!(m.total_trades, 0);
        assert!((m.win_rate - 0.0).abs() < 1e-10);
        assert!((m.profit_factor - 0.0).abs() < 1e-10);
        assert!((m.sharpe_ratio - 0.0).abs() < 1e-10);
        assert!((m.max_drawdown_pips - 0.0).abs() < 1e-10);
        assert!((m.net_pnl_pips - 0.0).abs() < 1e-10);
    }

    #[test]
    fn test_composite_score_perfect_metrics() {
        // Sharpe=2.0, R²=0.95, PF=3.0, DD=5%, 150 trades, 60% win
        let score = super::compute_composite_score(2.0, 0.95, 3.0, 5.0, 150, 0.60);
        // Each component: sharpe=2/3≈0.667, r2=0.95, pf=3/5=0.6, dd=1-5/50=0.9, trades=(150-30)/170≈0.706, wr=0.6
        // Weighted: 0.25*0.667 + 0.25*0.95 + 0.15*0.6 + 0.15*0.9 + 0.10*0.706 + 0.10*0.6
        let expected = 0.25 * (2.0 / 3.0) + 0.25 * 0.95 + 0.15 * 0.6 + 0.15 * 0.9 + 0.10 * (120.0 / 170.0) + 0.10 * 0.6;
        assert!((score - expected).abs() < 1e-10, "got {score}, expected {expected}");
        assert!(score > 0.6, "Good strategy should score > 0.6, got {score}");
    }

    #[test]
    fn test_composite_score_zero_trades_penalised() {
        // Sharpe=0 triggers hard gate -> score = 0
        let score = super::compute_composite_score(0.0, 0.0, 0.0, 0.0, 0, 0.0);
        assert_eq!(score, 0.0, "Sharpe=0 should trigger hard gate, got {score}");
    }

    #[test]
    fn test_composite_score_negative_sharpe_gate() {
        // Negative Sharpe -> hard gate -> score = 0 regardless of other metrics
        let score = super::compute_composite_score(-0.5, 0.95, 3.0, 5.0, 150, 0.60);
        assert_eq!(score, 0.0, "Negative Sharpe should gate to 0, got {score}");
    }

    #[test]
    fn test_composite_score_high_dd_penalty() {
        // Good Sharpe but terrible drawdown
        let good_dd = super::compute_composite_score(1.5, 0.8, 2.0, 10.0, 100, 0.55);
        let bad_dd = super::compute_composite_score(1.5, 0.8, 2.0, 45.0, 100, 0.55);
        assert!(good_dd > bad_dd, "High DD should reduce score: good={good_dd} bad={bad_dd}");
    }

    #[test]
    fn test_composite_score_clamping() {
        // Extreme values should be clamped
        let score = super::compute_composite_score(10.0, 1.5, 100.0, -5.0, 1000, 1.5);
        assert!(score <= 1.0, "Composite must be <= 1.0, got {score}");
        assert!(score >= 0.0, "Composite must be >= 0.0, got {score}");
    }

    #[test]
    fn test_score_mode_from_str() {
        assert_eq!(ScoreMode::from_str_opt(Some("sharpe")), ScoreMode::Sharpe);
        assert_eq!(ScoreMode::from_str_opt(Some("composite")), ScoreMode::Composite);
        assert_eq!(ScoreMode::from_str_opt(None), ScoreMode::Composite);
    }
}
