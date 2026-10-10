use repo_ranger_core::ast::{CodeSymbol, SymbolKind};
use repo_ranger_core::cache::CacheManager;
use repo_ranger_core::db::{CodeDatabase, IndexedFile};
use std::fs;
use std::path::PathBuf;

fn setup_temp_cache(sub: &str) -> (PathBuf, CacheManager) {
    let tmp = std::env::temp_dir()
        .join("repo_ranger_test_cache")
        .join(sub);
    let _ = fs::remove_dir_all(&tmp);
    fs::create_dir_all(&tmp).expect("Failed to create temp cache dir");
    let cm = CacheManager::new(tmp.clone(), 250 * 1024 * 1024);
    (tmp, cm)
}

#[test]
fn test_cache_save_and_load() {
    let (dir, cache) = setup_temp_cache("save_load");

    let mut db = CodeDatabase::new_in_memory().expect("Failed to create in-memory db");
    let files = [IndexedFile {
        path: "src/main.rs".to_string(),
        content: "fn main() { println!(\"hello\"); }".to_string(),
        symbols: vec![CodeSymbol {
            name: "main".to_string(),
            kind: SymbolKind::Function,
            signature: "fn main()".to_string(),
            start_line: 1,
            end_line: 1,
        }],
    }];
    db.index(&files).expect("Index failed");

    let merkle_root = "deadbeef0123456789abcdef";
    assert!(!cache.has(merkle_root));

    let saved_path = cache.save(merkle_root, &db).expect("Save failed");
    assert!(saved_path.is_file());
    assert!(cache.has(merkle_root));

    let restored = cache
        .load(merkle_root)
        .expect("Load failed")
        .expect("Cache entry missing");

    let hits = restored.search("println", 10).expect("Search failed");
    assert_eq!(hits.len(), 1);
    assert_eq!(hits[0].file_path, "src/main.rs");

    let syms = restored.find_symbol("main").expect("Find symbol failed");
    assert_eq!(syms.len(), 1);
    assert_eq!(syms[0].name, "main");

    let _ = fs::remove_dir_all(&dir);
}

#[test]
fn test_cache_miss_returns_none() {
    let (dir, cache) = setup_temp_cache("miss");
    let res = cache.load("non_existent_hash").expect("Load failed");
    assert!(res.is_none());
    assert!(!cache.has("non_existent_hash"));
    let _ = fs::remove_dir_all(&dir);
}

#[test]
fn test_atomic_write_no_tmp_leftover() {
    let (dir, cache) = setup_temp_cache("atomic");
    let db = CodeDatabase::new_in_memory().expect("Failed to create in-memory db");
    let merkle_root = "atomictest123";

    cache.save(merkle_root, &db).expect("Save failed");

    let mut tmp_found = false;
    for entry in fs::read_dir(&dir).expect("Read dir failed") {
        let path = entry.expect("Entry error").path();
        if path
            .file_name()
            .and_then(|n| n.to_str())
            .unwrap_or("")
            .contains(".tmp_")
        {
            tmp_found = true;
        }
    }
    assert!(!tmp_found);
    let _ = fs::remove_dir_all(&dir);
}

#[test]
fn test_lru_quota_eviction() {
    let tmp = std::env::temp_dir()
        .join("repo_ranger_test_cache")
        .join("quota");
    let _ = fs::remove_dir_all(&tmp);
    fs::create_dir_all(&tmp).expect("Failed to create temp cache dir");

    let mut db1 = CodeDatabase::new_in_memory().expect("DB1 failed");
    let mut db2 = CodeDatabase::new_in_memory().expect("DB2 failed");
    let mut db3 = CodeDatabase::new_in_memory().expect("DB3 failed");

    let files1 = [IndexedFile {
        path: "f1.rs".to_string(),
        content: "const X: &str = \"hello 1\";".to_string(),
        symbols: vec![],
    }];
    let files2 = [IndexedFile {
        path: "f2.rs".to_string(),
        content: "const Y: &str = \"hello 2\";".to_string(),
        symbols: vec![],
    }];
    let files3 = [IndexedFile {
        path: "f3.rs".to_string(),
        content: "const Z: &str = \"hello 3\";".to_string(),
        symbols: vec![],
    }];

    db1.index(&files1).expect("Index 1 failed");
    db2.index(&files2).expect("Index 2 failed");
    db3.index(&files3).expect("Index 3 failed");

    let unconstrained = CacheManager::new(tmp.clone(), 10 * 1024 * 1024);
    unconstrained.save("hash1", &db1).expect("Save 1 failed");

    std::thread::sleep(std::time::Duration::from_millis(50));
    unconstrained.save("hash2", &db2).expect("Save 2 failed");

    std::thread::sleep(std::time::Duration::from_millis(50));
    unconstrained.save("hash3", &db3).expect("Save 3 failed");

    assert!(unconstrained.has("hash1"));
    assert!(unconstrained.has("hash2"));
    assert!(unconstrained.has("hash3"));

    let f2_size = fs::metadata(unconstrained.cache_path("hash2"))
        .expect("f2 meta")
        .len();
    let f3_size = fs::metadata(unconstrained.cache_path("hash3"))
        .expect("f3 meta")
        .len();
    let tight_quota = f2_size + f3_size + 1024;

    let tight_cache = CacheManager::new(tmp.clone(), tight_quota);
    let remaining = tight_cache.enforce_quota().expect("Enforce failed");
    assert!(remaining <= tight_quota);

    assert!(!tight_cache.has("hash1"));
    assert!(tight_cache.has("hash2"));
    assert!(tight_cache.has("hash3"));

    let _ = fs::remove_dir_all(&tmp);
}
