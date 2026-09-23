use repo_ranger_core::merkle::{hash_file, MerkleTree};
use repo_ranger_core::tarball::stream_tarball_in_memory;
use flate2::write::GzEncoder;
use flate2::Compression;
use tar::Builder;
use tar::Header;

#[test]
fn test_hash_file_deterministic() {
    let hash1 = hash_file("src/main.rs", b"fn main() {}");
    let hash2 = hash_file("src/main.rs", b"fn main() {}");
    assert_eq!(hash1, hash2);

    let hash_diff_content = hash_file("src/main.rs", b"fn main() { println!(); }");
    assert_ne!(hash1, hash_diff_content);

    let hash_diff_path = hash_file("src/lib.rs", b"fn main() {}");
    assert_ne!(hash1, hash_diff_path);
}

#[test]
fn test_domain_separation_collision_resistance() {
    let hash_a = hash_file("ab", b"cd");
    let hash_b = hash_file("a", b"bcd");
    assert_ne!(hash_a, hash_b);
}

#[test]
fn test_empty_tree() {
    let tree = MerkleTree::new();
    assert!(tree.is_empty());
    assert_eq!(tree.len(), 0);

    let root = tree.root_hash();
    assert_ne!(root, [0u8; 32]);
    assert_eq!(tree.root_hash_hex().len(), 64);
}

#[test]
fn test_order_independence() {
    let mut tree1 = MerkleTree::new();
    tree1.add_file("src/lib.rs", b"pub fn run() {}");
    tree1.add_file("src/main.rs", b"fn main() {}");
    tree1.add_file("Cargo.toml", b"[package]");

    let mut tree2 = MerkleTree::new();
    tree2.add_file("Cargo.toml", b"[package]");
    tree2.add_file("src/main.rs", b"fn main() {}");
    tree2.add_file("src/lib.rs", b"pub fn run() {}");

    assert_eq!(tree1.root_hash(), tree2.root_hash());
    assert_eq!(tree1.root_hash_hex(), tree2.root_hash_hex());
}

#[test]
fn test_tree_diff() {
    let mut old_tree = MerkleTree::new();
    old_tree.add_file("src/main.rs", b"fn main() { 1 }");
    old_tree.add_file("src/lib.rs", b"pub fn a() {}");
    old_tree.add_file("README.md", b"# Title");

    let mut new_tree = MerkleTree::new();
    new_tree.add_file("src/main.rs", b"fn main() { 2 }");
    new_tree.add_file("src/lib.rs", b"pub fn a() {}");
    new_tree.add_file("Cargo.toml", b"[package]");

    let diff = old_tree.diff(&new_tree);

    assert_eq!(diff.added, vec!["Cargo.toml"]);
    assert_eq!(diff.modified, vec!["src/main.rs"]);
    assert_eq!(diff.removed, vec!["README.md"]);
}

#[test]
fn test_stream_tarball_merkle_integration() {
    let mut encoder = GzEncoder::new(Vec::new(), Compression::default());
    {
        let mut builder = Builder::new(&mut encoder);

        let content1 = b"fn main() {}";
        let mut header1 = Header::new_gnu();
        header1.set_size(content1.len() as u64);
        header1.set_mode(0o644);
        header1.set_cksum();
        builder
            .append_data(&mut header1, "repo/src/main.rs", &content1[..])
            .expect("Failed to append file 1");

        let content2 = b"pub fn test() {}";
        let mut header2 = Header::new_gnu();
        header2.set_size(content2.len() as u64);
        header2.set_mode(0o644);
        header2.set_cksum();
        builder
            .append_data(&mut header2, "repo/src/lib.rs", &content2[..])
            .expect("Failed to append file 2");

        builder.finish().expect("Failed to finish archive");
    }
    let tar_gz_bytes = encoder.finish().expect("Failed to finish gzip");

    let mut merkle = MerkleTree::new();
    let stats = stream_tarball_in_memory(&tar_gz_bytes, |path, content| {
        merkle.add_file(path, content);
        Ok(())
    })
    .expect("Decompression failed");

    assert_eq!(stats.files_processed, 2);
    assert_eq!(merkle.len(), 2);
    assert_eq!(merkle.root_hash_hex().len(), 64);
}
