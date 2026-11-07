//! When to restart a core that stopped on its own (§5.6, D-52): at once the first time, then back
//! off 1, 2, 4, 8, 16, then 30 s. A core that ran for a minute counts as healthy again, and
//! 5 crashes within 5 minutes switch on safe mode.

use std::collections::VecDeque;
use std::time::{Duration, Instant};

pub const BACKOFF_MAX: Duration = Duration::from_secs(30);
pub const CRASH_WINDOW: Duration = Duration::from_secs(5 * 60);
pub const SAFE_MODE_AFTER: usize = 5;
pub const STABLE_AFTER: Duration = Duration::from_secs(60);

/// What to do after a crash.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Decision {
    pub delay: Duration,
    pub safe_mode: bool,
    /// True only for the crash that switched safe mode on.
    pub entered_safe_mode: bool,
    pub recent_crashes: usize,
}

#[derive(Debug, Default)]
pub struct RestartPolicy {
    crashes: VecDeque<Instant>,
    failures_in_a_row: u32,
    ready_since: Option<Instant>,
    safe_mode: bool,
}

impl RestartPolicy {
    pub fn safe_mode(&self) -> bool {
        self.safe_mode
    }

    /// The core printed its READY line.
    pub fn on_ready(&mut self, now: Instant) {
        self.ready_since = Some(now);
    }

    /// The core stopped without being asked to (crash, kill, startup failure, READY timeout).
    pub fn on_crash(&mut self, now: Instant) -> Decision {
        if let Some(since) = self.ready_since.take()
            && now.saturating_duration_since(since) >= STABLE_AFTER
        {
            self.failures_in_a_row = 0;
        }
        self.crashes.push_back(now);
        while let Some(&first) = self.crashes.front() {
            if now.saturating_duration_since(first) > CRASH_WINDOW {
                self.crashes.pop_front();
            } else {
                break;
            }
        }
        let entered_safe_mode = !self.safe_mode && self.crashes.len() >= SAFE_MODE_AFTER;
        self.safe_mode |= entered_safe_mode;
        let delay = backoff(self.failures_in_a_row);
        self.failures_in_a_row = self.failures_in_a_row.saturating_add(1);
        Decision {
            delay,
            safe_mode: self.safe_mode,
            entered_safe_mode,
            recent_crashes: self.crashes.len(),
        }
    }
}

/// No wait for the first failure in a row (Sharan's choice at S04, so a one-off crash is back
/// within the 3 s target); then 1 s, 2 s, 4 s, 8 s, 16 s, and 30 s for every later one.
pub fn backoff(failures_before: u32) -> Duration {
    match failures_before {
        0 => Duration::ZERO,
        n => Duration::from_secs(1u64 << (n - 1).min(5)).min(BACKOFF_MAX),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn secs(n: u64) -> Duration {
        Duration::from_secs(n)
    }

    #[test]
    fn first_retry_is_immediate_then_backoff_doubles_up_to_thirty_seconds() {
        let delays: Vec<u64> = (0..9).map(|n| backoff(n).as_secs()).collect();
        assert_eq!(delays, [0, 1, 2, 4, 8, 16, 30, 30, 30]);
    }

    #[test]
    fn five_crashes_within_five_minutes_switch_on_safe_mode() {
        let t0 = Instant::now();
        let mut policy = RestartPolicy::default();
        for n in 0..4 {
            let decision = policy.on_crash(t0 + secs(10 * n));
            assert!(!decision.safe_mode);
        }
        let fifth = policy.on_crash(t0 + secs(50));
        assert!(fifth.safe_mode && fifth.entered_safe_mode);
        assert_eq!(fifth.recent_crashes, 5);
        let sixth = policy.on_crash(t0 + secs(60));
        assert!(sixth.safe_mode && !sixth.entered_safe_mode);
        assert!(policy.safe_mode());
    }

    #[test]
    fn crashes_older_than_five_minutes_do_not_count() {
        let t0 = Instant::now();
        let mut policy = RestartPolicy::default();
        for n in 0..10 {
            policy.on_ready(t0 + secs(90 * n));
            let decision = policy.on_crash(t0 + secs(90 * n + 89));
            assert!(!decision.safe_mode, "crash {n}");
            assert!(decision.recent_crashes <= 4);
        }
    }

    #[test]
    fn a_minute_of_healthy_running_resets_the_backoff() {
        let t0 = Instant::now();
        let mut policy = RestartPolicy::default();
        assert_eq!(policy.on_crash(t0).delay, secs(0));
        assert_eq!(policy.on_crash(t0 + secs(2)).delay, secs(1));
        policy.on_ready(t0 + secs(5));
        assert_eq!(policy.on_crash(t0 + secs(20)).delay, secs(2)); // not stable yet
        policy.on_ready(t0 + secs(30));
        assert_eq!(policy.on_crash(t0 + secs(95)).delay, secs(0)); // ran 65 s
    }
}
