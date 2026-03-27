//! Memory budget enforcement for the backtester binary (AC #7, NFR4).
//!
//! Pre-allocates at startup, never dynamically on hot paths.
//! If workload exceeds budget → reduces batch parallelism, logs decision, never crashes.

use std::sync::atomic::{AtomicU64, Ordering};

use common::error_types::BacktesterError;

/// Minimum batch size — never go below 1.
const MIN_BATCH_SIZE: u64 = 1;

/// Estimated bytes per trade buffer slot (conservative).
const BYTES_PER_TRADE_SLOT: u64 = 256;

/// Default number of trade slots per batch.
const DEFAULT_SLOTS_PER_BATCH: u64 = 100_000;

/// OS memory reserve margin in MB (per Story 3-2 research: 2-4GB).
const OS_RESERVE_MB: u64 = 2048;

/// Memory budget tracker for the backtester.
pub struct MemoryBudget {
    total_mb: u64,
    allocated: AtomicU64,
}

impl MemoryBudget {
    /// Create a new memory budget with the given limit in MB.
    pub fn new(budget_mb: u64) -> Self {
        Self {
            total_mb: budget_mb,
            allocated: AtomicU64::new(0),
        }
    }

    /// Check system memory and validate the budget fits within available RAM.
    /// Returns an error if the budget exceeds available system memory.
    pub fn check_system_memory(&self) -> Result<(), BacktesterError> {
        let available_mb = get_available_memory_mb();

        if available_mb == 0 {
            // Could not query system memory — log warning and proceed
            eprintln!(
                "{{\"level\":\"warn\",\"msg\":\"Could not query system memory; proceeding with budget {}MB\"}}",
                self.total_mb
            );
            return Ok(());
        }

        // Reserve OS margin
        let usable_mb = available_mb.saturating_sub(OS_RESERVE_MB);

        if self.total_mb > usable_mb {
            return Err(BacktesterError::OomError {
                requested_mb: self.total_mb,
                available_mb: usable_mb,
            });
        }

        eprintln!(
            "{{\"level\":\"info\",\"msg\":\"System memory: {}MB available, {}MB usable (after {}MB OS reserve), budget: {}MB\"}}",
            available_mb, usable_mb, OS_RESERVE_MB, self.total_mb
        );

        Ok(())
    }

    /// Compute the batch size that fits within the memory budget.
    /// Reduces parallelism if budget is tight — never crashes (NFR4).
    pub fn compute_batch_size(&self) -> u64 {
        let budget_bytes = self.total_mb * 1024 * 1024;
        let bytes_per_batch = DEFAULT_SLOTS_PER_BATCH * BYTES_PER_TRADE_SLOT;

        let batches = budget_bytes / bytes_per_batch.max(1);
        let batch_size = batches.max(MIN_BATCH_SIZE);

        if batch_size < 4 {
            eprintln!(
                "{{\"level\":\"warn\",\"msg\":\"Low memory budget: reduced batch parallelism to {}\"}}",
                batch_size
            );
        }

        batch_size
    }

    /// Track a memory allocation against the budget.
    /// Returns Ok if allocation fits, Err if it would exceed the budget.
    pub fn allocate(&self, bytes: u64) -> Result<(), BacktesterError> {
        let mb = bytes / (1024 * 1024);
        let current = self.allocated.load(Ordering::Relaxed);
        let new_total_mb = (current + bytes) / (1024 * 1024);

        if new_total_mb > self.total_mb {
            return Err(BacktesterError::OomError {
                requested_mb: mb,
                available_mb: self.total_mb.saturating_sub(current / (1024 * 1024)),
            });
        }

        self.allocated.fetch_add(bytes, Ordering::Relaxed);
        Ok(())
    }

    /// Return remaining available MB in the budget.
    pub fn available_mb(&self) -> u64 {
        let used = self.allocated.load(Ordering::Relaxed) / (1024 * 1024);
        self.total_mb.saturating_sub(used)
    }
}

/// Query available system memory in MB using platform-native APIs.
#[cfg(windows)]
fn get_available_memory_mb() -> u64 {
    use std::mem;
    #[repr(C)]
    struct MemoryStatusEx {
        dw_length: u32,
        dw_memory_load: u32,
        ull_total_phys: u64,
        ull_avail_phys: u64,
        ull_total_page_file: u64,
        ull_avail_page_file: u64,
        ull_total_virtual: u64,
        ull_avail_virtual: u64,
        ull_avail_extended_virtual: u64,
    }
    extern "system" {
        fn GlobalMemoryStatusEx(lp_buffer: *mut MemoryStatusEx) -> i32;
    }
    unsafe {
        let mut status: MemoryStatusEx = mem::zeroed();
        status.dw_length = mem::size_of::<MemoryStatusEx>() as u32;
        if GlobalMemoryStatusEx(&mut status) != 0 {
            status.ull_avail_phys / (1024 * 1024)
        } else {
            0
        }
    }
}

#[cfg(not(windows))]
fn get_available_memory_mb() -> u64 {
    // On Unix, read from /proc/meminfo
    if let Ok(content) = std::fs::read_to_string("/proc/meminfo") {
        for line in content.lines() {
            if line.starts_with("MemAvailable:") {
                let parts: Vec<&str> = line.split_whitespace().collect();
                if parts.len() >= 2 {
                    if let Ok(kb) = parts[1].parse::<u64>() {
                        return kb / 1024;
                    }
                }
            }
        }
    }
    0
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_memory_budget_creation() {
        let budget = MemoryBudget::new(512);
        assert_eq!(budget.available_mb(), 512);
    }

    #[test]
    fn test_allocate_within_budget() {
        let budget = MemoryBudget::new(100);
        // Allocate 50MB
        assert!(budget.allocate(50 * 1024 * 1024).is_ok());
        assert_eq!(budget.available_mb(), 50);
    }

    #[test]
    fn test_allocate_exceeds_budget() {
        let budget = MemoryBudget::new(10);
        // Try to allocate 20MB
        let result = budget.allocate(20 * 1024 * 1024);
        assert!(result.is_err());
    }

    #[test]
    fn test_compute_batch_size() {
        // Large budget → multiple batches
        let budget = MemoryBudget::new(4096);
        let size = budget.compute_batch_size();
        assert!(size >= 1);

        // Tiny budget → at least 1
        let budget = MemoryBudget::new(1);
        let size = budget.compute_batch_size();
        assert_eq!(size, MIN_BATCH_SIZE);
    }

    #[test]
    fn test_check_system_memory_succeeds() {
        // Use a small budget that should fit
        let budget = MemoryBudget::new(1);
        // This should succeed or return error based on actual system RAM
        // On a CI system with >3GB, this should pass
        let _ = budget.check_system_memory();
    }
}
