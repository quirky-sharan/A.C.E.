//! A Windows Job Object that ends every process in it (§5.6, D-52). Each core run gets its own job:
//! `terminate` stops the whole tree (in dev that is uv -> python), and because the job kills its
//! processes when its last handle closes, Windows cleans up even if the shell itself crashes.
//! Docs: https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects

use std::io;
use std::os::windows::io::AsRawHandle;
use std::process::Child;

use windows_sys::Win32::Foundation::{CloseHandle, HANDLE};
use windows_sys::Win32::System::JobObjects::{
    AssignProcessToJobObject, CreateJobObjectW, JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE,
    JOBOBJECT_BASIC_LIMIT_INFORMATION, JOBOBJECT_EXTENDED_LIMIT_INFORMATION,
    JobObjectExtendedLimitInformation, SetInformationJobObject, TerminateJobObject,
};

pub struct Job(HANDLE);

// SAFETY: a job handle is a kernel handle that any thread may use; `Job` owns it exclusively.
unsafe impl Send for Job {}

impl Job {
    /// A new unnamed job whose processes all end when its handle closes.
    pub fn kill_on_close() -> io::Result<Self> {
        // SAFETY: default security, no name.
        let handle = unsafe { CreateJobObjectW(std::ptr::null(), std::ptr::null()) };
        if handle.is_null() {
            return Err(io::Error::last_os_error());
        }
        let job = Job(handle);
        let info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION {
            BasicLimitInformation: JOBOBJECT_BASIC_LIMIT_INFORMATION {
                LimitFlags: JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE,
                ..Default::default()
            },
            ..Default::default()
        };
        // SAFETY: `info` is a valid JOBOBJECT_EXTENDED_LIMIT_INFORMATION and the size matches.
        let ok = unsafe {
            SetInformationJobObject(
                job.0,
                JobObjectExtendedLimitInformation,
                (&raw const info).cast(),
                size_of::<JOBOBJECT_EXTENDED_LIMIT_INFORMATION>() as u32,
            )
        };
        if ok == 0 {
            return Err(io::Error::last_os_error());
        }
        Ok(job)
    }

    /// Put `child` (and every process it starts from now on) into the job.
    pub fn assign(&self, child: &Child) -> io::Result<()> {
        // SAFETY: both handles stay valid for the duration of the call.
        let ok = unsafe { AssignProcessToJobObject(self.0, child.as_raw_handle()) };
        if ok == 0 {
            Err(io::Error::last_os_error())
        } else {
            Ok(())
        }
    }

    /// End every process in the job now.
    pub fn terminate(&self, exit_code: u32) -> io::Result<()> {
        // SAFETY: the handle is valid while `self` lives.
        let ok = unsafe { TerminateJobObject(self.0, exit_code) };
        if ok == 0 {
            Err(io::Error::last_os_error())
        } else {
            Ok(())
        }
    }

    #[cfg(test)]
    fn active_processes(&self) -> u32 {
        use windows_sys::Win32::System::JobObjects::{
            JOBOBJECT_BASIC_ACCOUNTING_INFORMATION, JobObjectBasicAccountingInformation,
            QueryInformationJobObject,
        };
        let mut info = JOBOBJECT_BASIC_ACCOUNTING_INFORMATION::default();
        // SAFETY: `info` is writable and its size is passed along.
        let ok = unsafe {
            QueryInformationJobObject(
                self.0,
                JobObjectBasicAccountingInformation,
                (&raw mut info).cast(),
                size_of::<JOBOBJECT_BASIC_ACCOUNTING_INFORMATION>() as u32,
                std::ptr::null_mut(),
            )
        };
        assert_ne!(ok, 0, "{}", io::Error::last_os_error());
        info.ActiveProcesses
    }
}

impl Drop for Job {
    fn drop(&mut self) {
        // SAFETY: we own the handle. Closing the last handle ends whatever still runs in the job.
        unsafe {
            CloseHandle(self.0);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::os::windows::process::CommandExt;
    use std::process::{Command, Stdio};
    use std::thread::sleep;
    use std::time::{Duration, Instant};

    const CREATE_NO_WINDOW: u32 = 0x0800_0000;

    /// cmd.exe starts ping.exe, so the job holds a two-level tree like `uv run` -> python.
    fn spawn_tree(job: &Job) -> Child {
        let child = Command::new("cmd")
            .args(["/D", "/C", "ping -n 30 127.0.0.1 >NUL"])
            .stdin(Stdio::null())
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .creation_flags(CREATE_NO_WINDOW)
            .spawn()
            .expect("cmd.exe starts");
        job.assign(&child).expect("assigned to the job");
        let deadline = Instant::now() + Duration::from_secs(10);
        while job.active_processes() < 2 {
            assert!(Instant::now() < deadline, "ping never started");
            sleep(Duration::from_millis(20));
        }
        child
    }

    fn exits_soon(child: &mut Child) -> bool {
        let deadline = Instant::now() + Duration::from_secs(5);
        while Instant::now() < deadline {
            if child.try_wait().expect("try_wait").is_some() {
                return true;
            }
            sleep(Duration::from_millis(20));
        }
        false
    }

    #[test]
    fn terminate_ends_the_whole_tree() {
        let job = Job::kill_on_close().unwrap();
        let mut child = spawn_tree(&job);
        job.terminate(1).unwrap();
        assert!(exits_soon(&mut child));
        assert_eq!(job.active_processes(), 0); // the grandchild is gone too
    }

    #[test]
    fn closing_the_job_ends_the_tree() {
        let job = Job::kill_on_close().unwrap();
        let mut child = spawn_tree(&job);
        drop(job); // what happens when the shell exits or crashes
        assert!(exits_soon(&mut child));
    }
}
