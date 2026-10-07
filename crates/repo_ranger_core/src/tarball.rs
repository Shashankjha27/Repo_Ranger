use flate2::read::GzDecoder;
//use flate2::Status::Ok;
use std::io::{Cursor, Read};
use std::path::{Component, PathBuf};
use sysinfo::System;
use tar::Archive;
use thiserror::Error;

#[derive(Error, Debug)]
pub enum TarballError {
    #[error("I/O error during decompression: {0}")]
    Io(#[from] std::io::Error),
    #[error("Invalid UTF-8 in entry path: {0}")]
    InvalidPath(String),
    #[error("Callback error: {0}")]
    CallbackError(String),
}

#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct TarballStats {
    pub files_processed: usize,
    pub files_skipped_oversized: usize,
    pub bytes_decompressed: u64,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct RawFile {
    pub path: String,
    pub content: Vec<u8>,
}

pub fn get_available_ram_bytes() -> u64 {
    let mut sys = System::new();
    sys.refresh_memory();
    sys.available_memory()
}

pub fn compute_max_file_size(available_ram: u64) -> u64 {
    let five_percent = available_ram / 20;
    five_percent.clamp(2 * 1024 * 1024, 100 * 1024 * 1024)
}

pub fn stream_tarball_in_memory<F>(
    tar_gz_bytes: &[u8],
    mut on_file: F,
) -> Result<TarballStats, TarballError>
where
    F: FnMut(&str, &[u8]) -> Result<(), TarballError>,
{
    let available_ram = get_available_ram_bytes();
    let max_file_size = compute_max_file_size(available_ram);

    let cursor = Cursor::new(tar_gz_bytes);
    let decoder = GzDecoder::new(cursor);
    let mut archive = Archive::new(decoder);

    let mut stats = TarballStats::default();
    let mut buf = Vec::with_capacity(64 * 1024);

    for entry_result in archive.entries()? {
        let mut entry = entry_result?;
        if !entry.header().entry_type().is_file() {
            continue;
        }

        let file_size = entry.header().size()?;
        if file_size > max_file_size {
            stats.files_skipped_oversized += 1;
            continue;
        }

        let raw_path = entry.path()?;
        let components: Vec<_> = raw_path.components().collect();
        if components.is_empty() {
            continue;
        }
        let stripped_path: PathBuf = if components.len() > 1 {
            components.into_iter().skip(1).collect()
        } else {
            components.into_iter().collect()
        };

        if stripped_path
            .components()
            .any(|c| matches!(c, Component::ParentDir))
        {
            continue;
        }

        let path_str = stripped_path
            .to_str()
            .ok_or_else(|| TarballError::InvalidPath(stripped_path.to_string_lossy().to_string()))?
            .to_string();

        buf.clear();
        entry.read_to_end(&mut buf)?;

        stats.files_processed += 1;
        stats.bytes_decompressed += buf.len() as u64;

        on_file(&path_str, &buf)?;
    }
    Ok(stats)
}

pub fn extract_tarball_in_memory(tar_gz_bytes: &[u8]) -> Result<Vec<RawFile>, TarballError> {
    let mut files = Vec::new();
    stream_tarball_in_memory(tar_gz_bytes, |path, content| {
        files.push(RawFile {
            path: path.to_string(),
            content: content.to_vec(),
        });
        Ok(())
    })?;
    Ok(files)
}
