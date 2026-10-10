use crate::db::CodeDatabase;
use rusqlite::backup::Backup;
use rusqlite::Connection;
use std::fs;
use std::path::{Path, PathBuff};
use std::time::Duration;
use thiserror::Error;

pub const DEFAULT_MAX_CACHE_BYTES: u64 = 250 * 1024 * 1024;
