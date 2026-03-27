//! Fold-aware evaluation support for CV-inside-objective optimization.
//!
//! When fold_config is Some, the engine evaluates each fold independently
//! and returns per-fold scores. When None, full dataset = single fold.

use serde::{Deserialize, Serialize};

/// Configuration for fold-aware evaluation.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FoldConfig {
    /// Fold boundaries as (start_bar, end_bar) pairs (inclusive).
    pub boundaries: Vec<(u64, u64)>,
    /// Number of bars to skip at fold boundaries to prevent look-ahead.
    pub embargo_bars: u64,
}

impl FoldConfig {
    /// Parse fold config from CLI args.
    pub fn from_args(
        fold_boundaries_json: Option<&str>,
        embargo_bars: Option<u64>,
    ) -> Result<Option<Self>, String> {
        match fold_boundaries_json {
            Some(json) => {
                let boundaries: Vec<Vec<u64>> = serde_json::from_str(json)
                    .map_err(|e| format!("Invalid fold_boundaries JSON: {e}"))?;

                let boundaries: Vec<(u64, u64)> = boundaries
                    .into_iter()
                    .map(|pair| {
                        if pair.len() != 2 {
                            Err("Each fold boundary must be [start, end]".to_string())
                        } else {
                            Ok((pair[0], pair[1]))
                        }
                    })
                    .collect::<Result<Vec<_>, _>>()?;

                Ok(Some(FoldConfig {
                    boundaries,
                    embargo_bars: embargo_bars.unwrap_or(0),
                }))
            }
            None => Ok(None),
        }
    }

    /// Check if a bar index falls within an embargo zone.
    pub fn is_embargo_bar(&self, bar_index: u64) -> bool {
        for &(_, end) in &self.boundaries {
            // Embargo zone: [end+1, end+embargo_bars]
            if bar_index > end && bar_index <= end + self.embargo_bars {
                return true;
            }
        }
        false
    }

    /// Get the fold ID for a bar index, or None if in embargo/outside folds.
    pub fn fold_for_bar(&self, bar_index: u64) -> Option<usize> {
        for (i, &(start, end)) in self.boundaries.iter().enumerate() {
            if bar_index >= start && bar_index <= end {
                return Some(i);
            }
        }
        None
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_fold_config_from_args() {
        let json = "[[0, 100], [110, 200], [210, 300]]";
        let config = FoldConfig::from_args(Some(json), Some(10)).unwrap().unwrap();
        assert_eq!(config.boundaries.len(), 3);
        assert_eq!(config.embargo_bars, 10);
    }

    #[test]
    fn test_fold_config_none() {
        let config = FoldConfig::from_args(None, None).unwrap();
        assert!(config.is_none());
    }

    #[test]
    fn test_embargo_bar_detection() {
        let config = FoldConfig {
            boundaries: vec![(0, 100), (110, 200)],
            embargo_bars: 5,
        };
        assert!(!config.is_embargo_bar(100));
        assert!(config.is_embargo_bar(101));
        assert!(config.is_embargo_bar(105));
        assert!(!config.is_embargo_bar(106));
        assert!(config.is_embargo_bar(201));
    }

    #[test]
    fn test_fold_for_bar() {
        let config = FoldConfig {
            boundaries: vec![(0, 100), (110, 200)],
            embargo_bars: 5,
        };
        assert_eq!(config.fold_for_bar(50), Some(0));
        assert_eq!(config.fold_for_bar(150), Some(1));
        assert_eq!(config.fold_for_bar(105), None); // Between folds
    }
}
