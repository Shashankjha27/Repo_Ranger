use blake3::Hasher;
use std::collections::BTreeMap;

pub fn hash_file(path: &str, content: &[u8]) -> [u8; 32] {
    let mut hasher = Hasher::new();
    hasher.update(path.as_bytes());
    hasher.update(b"\0");
    hasher.update(content);
    *hasher.finalize().as_bytes()
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct FileHash {
    pub path: String,
    pub hash: [u8; 32],
}

#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct TreeDiff {
    pub added: Vec<String>,
    pub modified: Vec<String>,
    pub removed: Vec<String>,
}

#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct MerkleTree {
    leaves: Vec<FileHash>,
}

impl MerkleTree {
    pub fn new() -> Self {
        Self { leaves: Vec::new() }
    }

    pub fn add_file(&mut self, path: &str, content: &[u8]) {
        let hash = hash_file(path, content);
        self.leaves.push(FileHash {
            path: path.to_string(),
            hash,
        });
    }

    pub fn add_leaf(&mut self, path: String, hash: [u8; 32]) {
        self.leaves.push(FileHash { path, hash });
    }

    pub fn len(&self) -> usize {
        self.leaves.len()
    }

    pub fn is_empty(&self) -> bool {
        self.leaves.is_empty()
    }

    pub fn leaves(&self) -> &[FileHash] {
        &self.leaves
    }

    pub fn root_hash(&self) -> [u8; 32] {
        if self.leaves.is_empty() {
            return *blake3::hash(b"").as_bytes();
        }

        let mut sorted = self.leaves.clone();
        sorted.sort_by(|a, b| a.path.cmp(&b.path));

        let mut current: Vec<[u8; 32]> = sorted.into_iter().map(|f| f.hash).collect();

        while current.len() > 1 {
            let mut next = Vec::with_capacity((current.len() + 1) / 2);
            for chunk in current.chunks(2) {
                let mut hasher = Hasher::new();
                hasher.update(&chunk[0]);
                if chunk.len() == 2 {
                    hasher.update(&chunk[1]);
                } else {
                    hasher.update(&chunk[0]);
                }
                next.push(*hasher.finalize().as_bytes());
            }
            current = next;
        }

        current[0]
    }

    pub fn root_hash_hex(&self) -> String {
        self.root_hash()
            .iter()
            .map(|b| format!("{:02x}", b))
            .collect()
    }

    pub fn diff(&self, other: &MerkleTree) -> TreeDiff {
        let old_map: BTreeMap<&str, &[u8; 32]> = self
            .leaves
            .iter()
            .map(|f| (f.path.as_str(), &f.hash))
            .collect();
        let new_map: BTreeMap<&str, &[u8; 32]> = other
            .leaves
            .iter()
            .map(|f| (f.path.as_str(), &f.hash))
            .collect();

        let mut diff = TreeDiff::default();

        for (path, new_hash) in &new_map {
            match old_map.get(path) {
                None => diff.added.push(path.to_string()),
                Some(old_hash) if old_hash != new_hash => diff.modified.push(path.to_string()),
                _ => {}
            }
        }

        for path in old_map.keys() {
            if !new_map.contains_key(path) {
                diff.removed.push(path.to_string());
            }
        }

        diff
    }
}
