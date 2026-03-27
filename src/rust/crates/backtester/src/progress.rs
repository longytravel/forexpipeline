//! Progress reporting for the backtester binary (AC #6, FR40).
//!
//! Writes periodic progress updates to `{output_dir}/progress.json`.
//! Python `BatchRunner.get_progress()` polls this file for status display.
//! Uses crash-safe write pattern: write → fsync → atomic rename.

use std::io;
use std::path::Path;

use serde::Serialize;

/// Progress report written to `progress.json` in the output directory.
#[derive(Debug, Serialize)]
pub struct ProgressReport {
    pub bars_processed: u64,
    pub total_bars: u64,
    pub estimated_seconds_remaining: f64,
    pub memory_used_mb: u64,
    pub updated_at: String, // ISO 8601 UTC
}

/// Write a progress report to `{output_dir}/progress.json` using crash-safe semantics.
///
/// Pattern: write to `.partial` → fsync → rename (NFR15).
pub fn write_progress(output_dir: &Path, report: &ProgressReport) -> io::Result<()> {
    let path = output_dir.join("progress.json");
    let partial = path.with_extension("json.partial");

    let json = serde_json::to_string_pretty(report)
        .map_err(|e| io::Error::new(io::ErrorKind::Other, e))?;

    // Write + fsync in one handle to avoid Windows file lock issues
    {
        use std::io::Write;
        let mut f = std::fs::File::create(&partial)?;
        f.write_all(json.as_bytes())?;
        f.flush()?;
        f.sync_all()?;
    } // handle dropped here — critical for Windows rename

    std::fs::rename(&partial, &path)?;
    Ok(())
}

/// Determine if progress should be reported based on bars processed and elapsed time.
///
/// Reports every N bars (default 10000) OR every T seconds (default 1),
/// whichever comes first — prevents I/O thrashing on high-frequency data.
pub fn should_report(
    bars_since_last: u64,
    secs_since_last: f64,
    bar_interval: u64,
    time_interval_s: f64,
) -> bool {
    bars_since_last >= bar_interval || secs_since_last >= time_interval_s
}

/// Generate ISO 8601 UTC timestamp without chrono dependency.
pub fn now_iso() -> String {
    let duration = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap_or_default();
    let secs = duration.as_secs();
    let days = secs / 86400;
    let rem = secs % 86400;
    let hours = rem / 3600;
    let mins = (rem % 3600) / 60;
    let s = rem % 60;
    let millis = duration.subsec_millis();

    let (year, month, day) = days_to_date(days);
    format!(
        "{year:04}-{month:02}-{day:02}T{hours:02}:{mins:02}:{s:02}.{millis:03}Z"
    )
}

fn days_to_date(days_since_epoch: u64) -> (u64, u64, u64) {
    let z = days_since_epoch + 719468;
    let era = z / 146097;
    let doe = z - era * 146097;
    let yoe = (doe - doe / 1460 + doe / 36524 - doe / 146096) / 365;
    let y = yoe + era * 400;
    let doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    let mp = (5 * doy + 2) / 153;
    let d = doy - (153 * mp + 2) / 5 + 1;
    let m = if mp < 10 { mp + 3 } else { mp - 9 };
    let y = if m <= 2 { y + 1 } else { y };
    (y, m, d)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_progress_report_serialization() {
        let report = ProgressReport {
            bars_processed: 5000,
            total_bars: 10000,
            estimated_seconds_remaining: 12.5,
            memory_used_mb: 256,
            updated_at: "2026-03-18T20:00:00.000Z".to_string(),
        };
        let json = serde_json::to_string(&report).unwrap();
        assert!(json.contains("\"bars_processed\":5000"));
        assert!(json.contains("\"total_bars\":10000"));
        assert!(json.contains("\"estimated_seconds_remaining\":12.5"));
    }

    #[test]
    fn test_write_progress_creates_file() {
        let dir = std::env::temp_dir().join("test_progress_write");
        std::fs::create_dir_all(&dir).unwrap();

        let report = ProgressReport {
            bars_processed: 100,
            total_bars: 200,
            estimated_seconds_remaining: 5.0,
            memory_used_mb: 128,
            updated_at: "2026-03-18T20:00:00.000Z".to_string(),
        };

        write_progress(&dir, &report).unwrap();

        let path = dir.join("progress.json");
        assert!(path.exists(), "progress.json should exist");

        // No .partial file should remain
        let partial = path.with_extension("json.partial");
        assert!(!partial.exists(), "no .partial file should remain after success");

        // Verify content
        let content = std::fs::read_to_string(&path).unwrap();
        assert!(content.contains("\"bars_processed\": 100"));

        // Cleanup
        std::fs::remove_dir_all(&dir).ok();
    }

    #[test]
    fn test_should_report_by_bars() {
        assert!(should_report(10000, 0.1, 10000, 1.0));
        assert!(!should_report(9999, 0.1, 10000, 1.0));
    }

    #[test]
    fn test_should_report_by_time() {
        assert!(should_report(1, 1.0, 10000, 1.0));
        assert!(!should_report(1, 0.5, 10000, 1.0));
    }
}
