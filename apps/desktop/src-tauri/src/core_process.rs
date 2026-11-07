//! One run of ace-core (§5.6, D-52): command line, environment, pipes and its own Job Object.
//! The core is a plain child process, not a Tauri sidecar: dev runs it from the checkout through
//! uv, and the frozen release build (S44) is a folder, which `externalBin` cannot ship.

use std::ffi::OsString;
use std::io::{self, BufRead, BufReader, Write};
use std::os::windows::process::CommandExt;
use std::path::{Path, PathBuf};
use std::process::{Child, ChildStdin, Command, ExitStatus, Stdio};
use std::sync::mpsc::Sender;
use std::thread;
use std::time::{Duration, Instant};

use crate::job::Job;
use crate::supervisor::Msg;

/// The core is a console program; this keeps it (and its children) from opening a console window.
const CREATE_NO_WINDOW: u32 = 0x0800_0000;
/// Exit code given to processes the shell has to end.
const KILLED: u32 = 1;

#[derive(Debug, Clone)]
pub struct CoreCommand {
    pub program: OsString,
    pub args: Vec<OsString>,
    pub current_dir: Option<PathBuf>,
}

impl CoreCommand {
    /// Debug builds: the core of this checkout, `uv run ace-core --dev --supervised`.
    pub fn development() -> Self {
        let core_dir = Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("..")
            .join("..")
            .join("..")
            .join("core");
        Self {
            program: "uv".into(),
            args: vec![
                "run".into(),
                "--project".into(),
                core_dir.clone().into_os_string(),
                "ace-core".into(),
                "--dev".into(),
                "--supervised".into(),
            ],
            current_dir: Some(core_dir),
        }
    }

    /// Release builds: the frozen core shipped next to the app (its packaging is decided at S44).
    pub fn bundled(resource_dir: &Path) -> Self {
        Self {
            program: resource_dir
                .join("core")
                .join("ace-core.exe")
                .into_os_string(),
            args: vec!["--supervised".into()],
            current_dir: None,
        }
    }
}

pub struct CoreProcess {
    child: Child,
    job: Job,
    stdin: Option<ChildStdin>,
}

impl CoreProcess {
    /// Start the core in a new job. Its stdout lines arrive on `tx` tagged with `generation`.
    pub fn spawn(
        command: &CoreCommand,
        token: &str,
        safe_mode: bool,
        generation: u64,
        tx: &Sender<Msg>,
    ) -> io::Result<Self> {
        let job = Job::kill_on_close()?;
        let mut cmd = Command::new(&command.program);
        cmd.args(&command.args);
        if safe_mode {
            cmd.arg("--safe-mode");
        }
        if let Some(dir) = &command.current_dir {
            cmd.current_dir(dir);
        }
        cmd.env("ACE_IPC_TOKEN", token)
            .env("ACE_IPC_PORT", "0")
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .creation_flags(CREATE_NO_WINDOW);
        let mut child = cmd.spawn()?;
        // A tiny gap remains between start and assignment; the core starts no process that early.
        if let Err(err) = job.assign(&child) {
            let _ = child.kill();
            let _ = child.wait();
            return Err(err);
        }

        if let Some(stdout) = child.stdout.take() {
            let tx = tx.clone();
            thread::Builder::new()
                .name("ace-core-stdout".into())
                .spawn(move || {
                    for line in BufReader::new(stdout).split(b'\n') {
                        let Ok(line) = line else { break };
                        let line = String::from_utf8_lossy(&line).into_owned();
                        if tx.send(Msg::CoreLine { generation, line }).is_err() {
                            return;
                        }
                    }
                    let _ = tx.send(Msg::CoreOutputClosed { generation });
                })?;
        }
        if let Some(stderr) = child.stderr.take() {
            thread::Builder::new()
                .name("ace-core-stderr".into())
                .spawn(move || {
                    // Debug builds show the core's dev log in the `tauri dev` terminal; release
                    // builds only drain the pipe (the core writes its real log to a file, D-46).
                    for line in BufReader::new(stderr).split(b'\n') {
                        let Ok(line) = line else { break };
                        if cfg!(debug_assertions) {
                            eprintln!("[core] {}", String::from_utf8_lossy(&line).trim_end());
                        }
                    }
                })?;
        }
        Ok(Self {
            stdin: child.stdin.take(),
            child,
            job,
        })
    }

    pub fn pid(&self) -> u32 {
        self.child.id()
    }

    /// Write one line to the core's stdin.
    pub fn send(&mut self, line: &str) -> io::Result<()> {
        let stdin = self.stdin.as_mut().ok_or_else(|| {
            io::Error::new(io::ErrorKind::BrokenPipe, "the core's stdin is closed")
        })?;
        stdin.write_all(line.as_bytes())?;
        stdin.flush()
    }

    pub fn exited(&mut self) -> Option<ExitStatus> {
        self.child.try_wait().ok().flatten()
    }

    /// Graceful stop (§5.6 step 6): close the core's stdin, wait up to `grace`, then end the tree.
    pub fn stop(mut self, grace: Duration) -> Option<ExitStatus> {
        drop(self.stdin.take());
        self.finish(grace)
    }

    /// Wait up to `wait` for the core to exit, then end whatever is left of its tree.
    pub fn finish(mut self, wait: Duration) -> Option<ExitStatus> {
        let deadline = Instant::now() + wait;
        let mut status = self.exited();
        while status.is_none() && Instant::now() < deadline {
            thread::sleep(Duration::from_millis(25));
            status = self.exited();
        }
        let _ = self.job.terminate(KILLED);
        status.or_else(|| self.child.wait().ok())
    }
}
