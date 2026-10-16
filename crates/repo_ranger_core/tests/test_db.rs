use repo_ranger_core::ast::{CodeSymbol, SymbolKind};
use repo_ranger_core::db::{CodeDatabase, IndexedFile};

#[test]
fn test_identifier_tokenization() {
    let mut db = CodeDatabase::new_in_memory().expect("Failed to create in-memory DB");

    let files = [
        IndexedFile {
            path: "src/tarball.rs".to_string(),
            content: "pub fn get_available_ram() -> u64 { 1024 }".to_string(),
            symbols: vec![CodeSymbol {
                name: "get_available_ram".to_string(),
                kind: SymbolKind::Function,
                signature: "pub fn get_available_ram() -> u64".to_string(),
                start_line: 1,
                end_line: 1,
            }],
        },
        IndexedFile {
            path: "src/other.rs".to_string(),
            content: "pub fn ram_monitor() { let ram = 100; }".to_string(),
            symbols: vec![],
        },
    ];

    db.index(&files).expect("Failed to index files");

    // Exact snake_case identifier matches only the file with that identifier
    let hits = db.search("get_available_ram", 10).expect("Search failed");
    assert_eq!(hits.len(), 1);
    assert_eq!(hits[0].file_path, "src/tarball.rs");

    // Dotted search matches because '.' is not in tokenchars
    let dot_hits = db.search("tarball", 10).expect("Dotted search failed");
    assert_eq!(dot_hits.len(), 1);
    assert_eq!(dot_hits[0].file_path, "src/tarball.rs");
}

#[test]
fn test_bm25_ranking_order() {
    let mut db = CodeDatabase::new_in_memory().expect("Failed to create in-memory DB");

    let files = [
        IndexedFile {
            path: "src/low_relevance.rs".to_string(),
            content: "fn process() { let token = 1; }".to_string(),
            symbols: vec![],
        },
        IndexedFile {
            path: "src/high_relevance.rs".to_string(),
            content: "fn token_parser() { let token = 1; let next_token = token; validate(token); }".to_string(),
            symbols: vec![],
        },
    ];

    db.index(&files).expect("Failed to index files");

    let hits = db.search("token", 10).expect("Search failed");
    assert_eq!(hits.len(), 2);
    // Highest frequency / density ranks first
    assert_eq!(hits[0].file_path, "src/high_relevance.rs");
    assert_eq!(hits[1].file_path, "src/low_relevance.rs");
}

#[test]
fn test_fts5_syntax_safety_special_chars() {
    let mut db = CodeDatabase::new_in_memory().expect("Failed to create in-memory DB");

    let files = [IndexedFile {
        path: "src/auth.py".to_string(),
        content: "@app.route('/login')\ndef login():\n    token = request.headers.get('auth-token')".to_string(),
        symbols: vec![],
    }];

    db.index(&files).expect("Failed to index files");

    // Queries with characters that normally break FTS5 (@, -, ., quotes)
    let queries = ["@app.route", "auth-token", "login()", "headers.get", "\"token\""];
    for q in queries {
        let result = db.search(q, 10);
        assert!(result.is_ok(), "Query '{}' triggered an FTS5 syntax error", q);
    }
}

#[test]
fn test_find_symbol_exact_lookup() {
    let mut db = CodeDatabase::new_in_memory().expect("Failed to create in-memory DB");

    let files = [IndexedFile {
        path: "src/models.rs".to_string(),
        content: "pub struct User { pub id: u64 }".to_string(),
        symbols: vec![CodeSymbol {
            name: "User".to_string(),
            kind: SymbolKind::Struct,
            signature: "pub struct User".to_string(),
            start_line: 1,
            end_line: 1,
        }],
    }];

    db.index(&files).expect("Failed to index files");

    let records = db.find_symbol("User").expect("Symbol lookup failed");
    assert_eq!(records.len(), 1);
    assert_eq!(records[0].name, "User");
    assert_eq!(records[0].kind, SymbolKind::Struct);
    assert_eq!(records[0].file_path, "src/models.rs");
    assert_eq!(records[0].start_line, 1);

    let empty = db.find_symbol("NonExistent").expect("Lookup failed");
    assert!(empty.is_empty());
}
