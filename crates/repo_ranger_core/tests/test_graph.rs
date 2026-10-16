use repo_ranger_core::ast::{CodeSymbol, SymbolKind};
use repo_ranger_core::db::IndexedFile;
use repo_ranger_core::graph::SymbolGraph;

#[test]
fn test_empty_graph() {
    let graph = SymbolGraph::build(&[]);
    assert_eq!(graph.symbol_count(), 0);
    assert_eq!(graph.edge_count(), 0);
    assert!(graph.top_symbols(5).is_empty());
}

#[test]
fn test_callers_and_callees_resolution() {
    let files = [
        IndexedFile {
            path: "src/service.rs".to_string(),
            content: "fn handle_request() {\n    validate_token();\n    fetch_data();\n}"
                .to_string(),
            symbols: vec![CodeSymbol {
                name: "handle_request".to_string(),
                kind: SymbolKind::Function,
                signature: "fn handle_request()".to_string(),
                start_line: 1,
                end_line: 4,
            }],
        },
        IndexedFile {
            path: "src/auth.rs".to_string(),
            content: "fn validate_token() {\n    fetch_data();\n}".to_string(),
            symbols: vec![CodeSymbol {
                name: "validate_token".to_string(),
                kind: SymbolKind::Function,
                signature: "fn validate_token()".to_string(),
                start_line: 1,
                end_line: 3,
            }],
        },
        IndexedFile {
            path: "src/db.rs".to_string(),
            content: "fn fetch_data() {\n    let x = 1;\n}".to_string(),
            symbols: vec![CodeSymbol {
                name: "fetch_data".to_string(),
                kind: SymbolKind::Function,
                signature: "fn fetch_data()".to_string(),
                start_line: 1,
                end_line: 3,
            }],
        },
    ];

    let graph = SymbolGraph::build(&files);

    assert_eq!(graph.symbol_count(), 3);
    assert_eq!(graph.edge_count(), 3);

    let handle_callees = graph.get_callees("handle_request");
    assert_eq!(handle_callees.len(), 2);
    assert!(handle_callees.contains(&"validate_token".to_string()));
    assert!(handle_callees.contains(&"fetch_data".to_string()));

    let fetch_callers = graph.get_callers("fetch_data");
    assert_eq!(fetch_callers.len(), 2);
    assert!(fetch_callers.contains(&"handle_request".to_string()));
    assert!(fetch_callers.contains(&"validate_token".to_string()));

    let validate_callers = graph.get_callers("validate_token");
    assert_eq!(validate_callers, vec!["handle_request".to_string()]);
}

#[test]
fn test_pagerank_centrality_ranking() {
    let files = [
        IndexedFile {
            path: "a.rs".to_string(),
            content: "fn caller_one() {\n    leaf_helper();\n}".to_string(),
            symbols: vec![CodeSymbol {
                name: "caller_one".to_string(),
                kind: SymbolKind::Function,
                signature: "fn caller_one()".to_string(),
                start_line: 1,
                end_line: 3,
            }],
        },
        IndexedFile {
            path: "b.rs".to_string(),
            content: "fn caller_two() {\n    leaf_helper();\n}".to_string(),
            symbols: vec![CodeSymbol {
                name: "caller_two".to_string(),
                kind: SymbolKind::Function,
                signature: "fn caller_two()".to_string(),
                start_line: 1,
                end_line: 3,
            }],
        },
        IndexedFile {
            path: "c.rs".to_string(),
            content: "fn leaf_helper() {\n    let val = 42;\n}".to_string(),
            symbols: vec![CodeSymbol {
                name: "leaf_helper".to_string(),
                kind: SymbolKind::Function,
                signature: "fn leaf_helper()".to_string(),
                start_line: 1,
                end_line: 3,
            }],
        },
    ];

    let graph = SymbolGraph::build(&files);

    let rank_leaf = graph.get_pagerank("leaf_helper");
    let rank_one = graph.get_pagerank("caller_one");
    let rank_two = graph.get_pagerank("caller_two");

    assert!(rank_leaf > rank_one);
    assert!(rank_leaf > rank_two);

    let top = graph.top_symbols(1);
    assert_eq!(top.len(), 1);
    assert_eq!(top[0].0, "leaf_helper");

    let sum = rank_leaf + rank_one + rank_two;
    assert!((sum - 1.0).abs() < 1e-4);
}

#[test]
fn test_self_recursion_edge_ignored() {
    let files = [IndexedFile {
        path: "rec.rs".to_string(),
        content: "fn factorial(n: u64) -> u64 {\n    factorial(n - 1)\n}".to_string(),
        symbols: vec![CodeSymbol {
            name: "factorial".to_string(),
            kind: SymbolKind::Function,
            signature: "fn factorial(n: u64) -> u64".to_string(),
            start_line: 1,
            end_line: 3,
        }],
    }];

    let graph = SymbolGraph::build(&files);
    assert_eq!(graph.symbol_count(), 1);
    assert_eq!(graph.edge_count(), 0);
    assert!(graph.get_callees("factorial").is_empty());
    assert!(graph.get_callers("factorial").is_empty());
}
