use crate::db::CodeDatabase;
use rusqlite::backup::Backup;
use rusqlite::Connection;
use std::fs;
use std::path::{Path, PathBuf};
use std::time::Duration;
use thiserror::Error;

pub const DEFAULT_MAX_CACHE_BYTES: u64 = 250 * 1024 * 1024;

#[derive(Error, Debug)]
pub enum CacheError {
    #[error("I/O error: {0}")]
    Io(#[from] std::io::Error),
    #[error("SQLite error: {0}")]
    Sqlite(#[from] rusqlite::Error),
}

#[derive(Debug, Clone)]
pub struct CacheManager {
    cache_dir: PathBuf,
    max_size_bytes: u64,
}

impl CacheManager {
    pub fn new(cache_dir: PathBuf, max_size_bytes: u64) -> Self {
        Self {
            cache_dir,
            max_size_bytes,
        }
    }

    pub fn default_dir() -> PathBuf {
        if let Ok(xdg) = std::env::var("XDG_CACHE_HOME") {
            if !xdg.is_empty() {
                return PathBuf::from(xdg).join("repo_ranger");
            }
        }
        if let Ok(home) = std::env::var("HOME") {
            if !home.is_empty() {
                return PathBuf::from(home).join(".cache").join("repo_ranger");
            }
        }
        PathBuf::from(".cache").join("repo_ranger")
    }

    pub fn new_default() -> Self {
        Self::new(Self::default_dir(), DEFAULT_MAX_CACHE_BYTES)
    }

    pub fn cache_dir(&self) -> &Path {
        &self.cache_dir
    }

    pub fn cache_path(&self, merkle_root: &str) -> PathBuf {
        self.cache_dir.join(format!("{}.sqlite", merkle_root))
    }

    pub fn has(&self, merkle_root: &str) -> bool {
        self.cache_path(merkle_root).is_file()
    }

    pub fn save(&self, merkle_root: &str, db: &CodeDatabase) -> Result<PathBuf, CacheError> {
        fs::create_dir_all(&self.cache_dir)?;

        let target_path = self.cache_path(merkle_root);
        let tmp_path =
            self.cache_dir()
                .join(format!("{}.tmp_{}.sqlite", merkle_root, std::process::id()));
        {
            let mut dst = Connection::open(&tmp_path)?;
            let backup = Backup::new(db.conn(), &mut dst)?;
            backup.run_to_completion(100, Duration::from_millis(1), None)?;
        }

        fs::rename(&tmp_path, &target_path)?;
        self.enforce_quota()?;
        Ok(target_path)
    }

    pub fn load(&self, merkle_root: &str) -> Result<Option<CodeDatabase>, CacheError> {
        let path = self.cache_path(merkle_root);
        if !path.is_file() {
            return Ok(None);
        }

        let src = Connection::open(&path)?;
        let mut dst = Connection::open_in_memory()?;
        {
            let backup = Backup::new(&src, &mut dst)?;
            backup.run_to_completion(100, Duration::from_millis(1), None)?;
        }

        Ok(Some(CodeDatabase::from_connection(dst)))
    }

    pub fn enforce_quota(&self) -> Result<u64, CacheError> {
        if !self.cache_dir().is_dir() {
            return Ok(0);
        }

        let mut entries = Vec::new();
        let mut total_size: u64 = 0;

        for entry_res in fs::read_dir(&self.cache_dir)? {
            let entry = entry_res?;
            let path = entry.path();
            if path.extension().and_then(|s| s.to_str()) == Some("sqlite")
                && !path
                    .file_name()
                    .and_then(|n| n.to_str())
                    .unwrap_or("")
                    .contains(".tmp_")
            {
                if let Ok(meta) = entry.metadata() {
                    let len = meta.len();
                    total_size += len;
                    let mtime = meta.modified().unwrap_or(std::time::SystemTime::UNIX_EPOCH);
                    entries.push((path, len, mtime));
                }
            }
        }

        if total_size <= self.max_size_bytes {
            return Ok(total_size);
        }

        entries.sort_by_key(|(_, _, mtime)| *mtime);

        for (path, len, _) in entries {
            if total_size <= self.max_size_bytes {
                break;
            }
            if fs::remove_file(&path).is_ok() {
                total_size = total_size.saturating_sub(len);
            }
        }

        Ok(total_size)
    }
}
