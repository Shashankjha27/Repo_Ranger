use repo_ranger_core::ast::{compress_batch, AstEngine, SymbolKind};

#[test]
fn test_compress_rust() {
    let source = r#"
/// Computes the sum.
pub fn calculate(a: i32, b: i32) -> i32 {
    let temp = a + b;
    temp * 2
}
"#;
    let compressed = AstEngine::compress("src/math.rs", source.as_bytes()).expect("Compression failed");
    assert!(compressed.contains("pub fn calculate(a: i32, b: i32) -> i32 { ... }"));
    assert!(compressed.contains("Computes the sum."));
    assert!(!compressed.contains("let temp = a + b;"));
}

#[test]
fn test_compress_python() {
    let source = r#"
class AuthManager:
    """Manages authentication."""
    def login(self, username: str) -> bool:
        session = create_session(username)
        return True
"#;
    let compressed = AstEngine::compress("auth.py", source.as_bytes()).expect("Compression failed");
    assert!(compressed.contains("class AuthManager:"));
    assert!(compressed.contains("def login(self, username: str) -> bool:"));
    assert!(!compressed.contains("create_session(username)"));
}

#[test]
fn test_compress_typescript_and_javascript() {
    let ts_source = r#"
export async function fetchUser(userId: string): Promise<User> {
    const response = await fetch(`/api/users/${userId}`);
    const data = await response.json();
    return data;
}
"#;
    let ts_compressed = AstEngine::compress("api.ts", ts_source.as_bytes()).expect("TS compression failed");
    assert!(ts_compressed.contains("export async function fetchUser(userId: string): Promise<User> { ... }"));
    assert!(!ts_compressed.contains("const response = await fetch"));

    let js_source = r#"
function renderBanner(title) {
    const el = document.getElementById("banner");
    el.innerText = title;
}
"#;
    let js_compressed = AstEngine::compress("banner.js", js_source.as_bytes()).expect("JS compression failed");
    assert!(js_compressed.contains("function renderBanner(title) { ... }"));
    assert!(!js_compressed.contains("document.getElementById"));
}

#[test]
fn test_compress_go() {
    let go_source = r#"
package main

func ProcessOrder(orderID string) (bool, error) {
    if orderID == "" {
        return false, errors.New("empty")
    }
    return true, nil
}
"#;
    let compressed = AstEngine::compress("order.go", go_source.as_bytes()).expect("Go compression failed");
    assert!(compressed.contains("func ProcessOrder(orderID string) (bool, error) { ... }"));
    assert!(!compressed.contains("errors.New"));
}

#[test]
fn test_compress_c_and_cpp() {
    let c_source = r#"
int calculate_hash(const char *key, int len) {
    int hash = 5381;
    for (int i = 0; i < len; i++) {
        hash = ((hash << 5) + hash) + key[i];
    }
    return hash;
}
"#;
    let compressed = AstEngine::compress("hash.c", c_source.as_bytes()).expect("C compression failed");
    assert!(compressed.contains("int calculate_hash(const char *key, int len) { ... }"));
    assert!(!compressed.contains("hash = ((hash << 5) + hash)"));
}

#[test]
fn test_compress_java() {
    let java_source = r#"
public class PaymentGateway {
    public boolean processPayment(double amount) {
        Database.log("Processing " + amount);
        return true;
    }
}
"#;
    let compressed = AstEngine::compress("PaymentGateway.java", java_source.as_bytes()).expect("Java compression failed");
    assert!(compressed.contains("public class PaymentGateway {"));
    assert!(compressed.contains("public boolean processPayment(double amount) { ... }"));
    assert!(!compressed.contains("Database.log"));
}

#[test]
fn test_extract_symbols_multi_language() {
    let rs_src = "pub struct User; pub fn get_user() {}";
    let rs_symbols = AstEngine::extract_symbols("user.rs", rs_src.as_bytes()).expect("Rust symbols failed");
    assert_eq!(rs_symbols.len(), 2);
    assert!(rs_symbols.iter().any(|s| s.name == "User" && s.kind == SymbolKind::Struct));
    assert!(rs_symbols.iter().any(|s| s.name == "get_user" && s.kind == SymbolKind::Function));

    let ts_src = "export interface Config {} export function init() {}";
    let ts_symbols = AstEngine::extract_symbols("config.ts", ts_src.as_bytes()).expect("TS symbols failed");
    assert_eq!(ts_symbols.len(), 2);
    assert!(ts_symbols.iter().any(|s| s.name == "Config" && s.kind == SymbolKind::Interface));
    assert!(ts_symbols.iter().any(|s| s.name == "init" && s.kind == SymbolKind::Function));

    let go_src = "package main\ntype Worker struct {}\nfunc Run() {}";
    let go_symbols = AstEngine::extract_symbols("worker.go", go_src.as_bytes()).expect("Go symbols failed");
    assert_eq!(go_symbols.len(), 2);
    assert!(go_symbols.iter().any(|s| s.name == "Worker" && s.kind == SymbolKind::Struct));
    assert!(go_symbols.iter().any(|s| s.name == "Run" && s.kind == SymbolKind::Function));
}

#[test]
fn test_unsupported_language_fallback() {
    let json_data = r#"{"name": "repo_ranger", "version": "0.1.0"}"#;
    let compressed = AstEngine::compress("package.json", json_data.as_bytes()).expect("Fallback failed");
    assert_eq!(compressed, json_data);
}

#[test]
fn test_syntax_error_tolerance() {
    let malformed_rust = r#"
pub fn valid_one() -> i32 { 42 }
pub fn broken( { this is broken syntax
pub fn valid_two() -> i32 { 100 }
"#;
    let compressed = AstEngine::compress("broken.rs", malformed_rust.as_bytes()).expect("Parse failed");
    assert!(compressed.contains("valid_one"));
    assert!(compressed.contains("valid_two"));
}

#[test]
fn test_rayon_batch_compression_multi_language() {
    let files = [
        ("src/main.rs", "fn main() { println!(\"hello\"); }"),
        ("app.py", "def run():\n    print('run')\n"),
        ("index.ts", "function start(): void { console.log('start'); }"),
        ("main.go", "package main\nfunc main() { fmt.Println(1) }"),
        ("main.c", "int main() { return 0; }"),
        ("App.java", "class App { public static void main(String[] args) { System.out.println(); } }"),
    ];

    let borrowed: Vec<(&str, &[u8])> = files.iter().map(|(p, c)| (*p, c.as_bytes())).collect();
    let results = compress_batch(&borrowed);

    assert_eq!(results.len(), 6);
    for res in results {
        let (path, compressed) = res.expect("Batch item failed");
        assert!(compressed.contains("{ ... }") || compressed.contains("..."), "File {} not compressed properly", path);
    }
}
