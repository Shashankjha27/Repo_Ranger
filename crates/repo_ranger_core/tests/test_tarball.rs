use flate2::write::GzEncoder;
use flate2::Compression;
use repo_ranger_core::tarball::{
    compute_max_file_size, extract_tarball_in_memory, get_available_ram_bytes,
    stream_tarball_in_memory, TarballError,
};
use std::sync::atomic::{AtomicUsize, Ordering};
use tar::Builder;
use tar::Header;

#[test]
fn test_get_available_ram_and_clamping() {
    let ram = get_available_ram_bytes();
    assert!(ram > 0);

    let clamp_low = compute_max_file_size(10 * 1024 * 1024);
    assert_eq!(clamp_low, 2 * 1024 * 1024);

    let clamp_high = compute_max_file_size(32 * 1024 * 1024 * 1024);
    assert_eq!(clamp_high, 100 * 1024 * 1024);
}

#[test]
fn test_stream_tarball_in_memory() {
    let mut encoder = GzEncoder::new(Vec::new(), Compression::default());
    {
        let mut builder = Builder::new(&mut encoder);

        let file1_content = b"fn main() {}";
        let mut header1 = Header::new_gnu();
        header1.set_size(file1_content.len() as u64);
        header1.set_mode(0o644);
        header1.set_cksum();
        builder
            .append_data(
                &mut header1,
                "octocat-hello-world-abc1234/src/main.rs",
                &file1_content.as_slice()[..],
            )
            .expect("Failed to append test file 1");

        let file2_content = b"test package content";
        let mut header2 = Header::new_gnu();
        header2.set_size(file2_content.len() as u64);
        header2.set_mode(0o644);
        header2.set_cksum();
        builder
            .append_data(
                &mut header2,
                "octocat-hello-world-abc1234/package.json",
                &file2_content.as_slice()[..],
            )
            .expect("Failed to append test file 2");

        builder.finish().expect("Failed to finish tar archive");
    }
    let tar_gz_bytes = encoder.finish().expect("Failed to finish gzip encoder");

    let streamed_count = AtomicUsize::new(0);
    let stats = stream_tarball_in_memory(&tar_gz_bytes, |path, content| {
        streamed_count.fetch_add(1, Ordering::SeqCst);
        if path == "src/main.rs" {
            assert_eq!(content, b"fn main() {}");
        } else if path == "package.json" {
            assert_eq!(content, b"test package content");
        }
        Ok(())
    })
    .expect("Streaming failed");

    assert_eq!(stats.files_processed, 2);
    assert_eq!(stats.files_skipped_oversized, 0);
    assert_eq!(streamed_count.load(Ordering::SeqCst), 2);
}

#[test]
fn test_extract_valid_tarball_in_memory() {
    let mut encoder = GzEncoder::new(Vec::new(), Compression::default());
    {
        let mut builder = Builder::new(&mut encoder);

        let file1_content = b"fn main() {}";
        let mut header1 = Header::new_gnu();
        header1.set_size(file1_content.len() as u64);
        header1.set_mode(0o644);
        header1.set_cksum();
        builder
            .append_data(
                &mut header1,
                "octocat-hello-world-abc1234/src/main.rs",
                &file1_content.as_slice()[..],
            )
            .expect("Failed to append test file 1");

        builder.finish().expect("Failed to finish tar archive");
    }
    let tar_gz_bytes = encoder.finish().expect("Failed to finish gzip encoder");

    let extracted = extract_tarball_in_memory(&tar_gz_bytes).expect("Decompression failed");
    assert_eq!(extracted.len(), 1);
    assert_eq!(extracted[0].path, "src/main.rs");
    assert_eq!(extracted[0].content, b"fn main() {}");
}

#[test]
fn test_strip_path_traversal_attempts() {
    let mut encoder = GzEncoder::new(Vec::new(), Compression::default());
    {
        let mut builder = Builder::new(&mut encoder);

        let malicious_content = b"malicious content";
        let mut header = Header::new_gnu();
        header.set_size(malicious_content.len() as u64);
        header.set_mode(0o644);

        let path_bytes = b"repo-root/../../etc/passwd";
        header.as_mut_bytes().as_mut_slice()[..path_bytes.len()].copy_from_slice(path_bytes);
        header.set_cksum();
        builder
            .append(&header, &malicious_content.as_slice()[..])
            .expect("Failed to append traversal path");

        builder.finish().expect("Failed to finish tar archive");
    }
    let tar_gz_bytes = encoder.finish().expect("Failed to finish gzip encoder");

    let extracted = extract_tarball_in_memory(&tar_gz_bytes).expect("Decompression failed");
    assert_eq!(extracted.len(), 0);
}

#[test]
fn test_early_exit_on_callback_error() {
    let mut encoder = GzEncoder::new(Vec::new(), Compression::default());
    {
        let mut builder = Builder::new(&mut encoder);

        let content = b"file content";
        let mut header = Header::new_gnu();
        header.set_size(content.len() as u64);
        header.set_mode(0o644);
        header.set_cksum();
        builder
            .append_data(&mut header, "repo/file1.rs", &content.as_slice()[..])
            .expect("Failed to append file 1");
        builder
            .append_data(&mut header, "repo/file2.rs", &content.as_slice()[..])
            .expect("Failed to append file 2");

        builder.finish().expect("Failed to finish tar archive");
    }
    let tar_gz_bytes = encoder.finish().expect("Failed to finish gzip encoder");

    let call_count = AtomicUsize::new(0);
    let result = stream_tarball_in_memory(&tar_gz_bytes, |_path, _content| {
        call_count.fetch_add(1, Ordering::SeqCst);
        Err(TarballError::CallbackError("cancel".to_string()))
    });

    assert!(result.is_err());
    assert_eq!(call_count.load(Ordering::SeqCst), 1);
}
