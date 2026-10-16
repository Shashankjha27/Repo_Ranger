use crate::ast::SymbolKind;
use crate::db::IndexedFile;
use std::collections::{HashMap, HashSet};

#[derive(Debug, Clone, Default, PartialEq)]
pub struct SymbolGraph {
    callees: HashMap<String, Vec<String>>,
    callers: HashMap<String, Vec<String>>,
    symbols: HashSet<String>,
    pagerank: HashMap<String, f64>,
}

impl SymbolGraph {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn symbol_count(&self) -> usize {
        self.symbols.len()
    }

    pub fn edge_count(&self) -> usize {
        self.callees.values().map(|v| v.len()).sum()
    }

    pub fn add_symbol(&mut self, name: String) {
        self.symbols.insert(name);
    }

    pub fn add_edge(&mut self, caller: &str, callee: &str) {
        if caller == callee {
            return;
        }
        self.symbols.insert(caller.to_string());
        self.symbols.insert(callee.to_string());

        let callee_list = self.callees.entry(caller.to_string()).or_default();
        if !callee_list.iter().any(|s| s == callee) {
            callee_list.push(callee.to_string());
        }

        let caller_list = self.callers.entry(callee.to_string()).or_default();
        if !caller_list.iter().any(|s| s == caller) {
            caller_list.push(caller.to_string());
        }
    }

    pub fn build(file: &[IndexedFile]) -> Self {
        let mut graph = Self::new();
        let mut known_symbols: HashSet<String> = HashSet::new();

        for file in file {
            for sym in &file.symbols {
                known_symbols.insert(sym.name.clone());
                graph.add_symbol(sym.name.clone());
            }
        }

        for file in file {
            let lines: Vec<&str> = file.content.lines().collect();

            for sym in &file.symbols {
                if sym.kind != SymbolKind::Function {
                    continue;
                }

                if sym.start_line == 0 || sym.start_line > lines.len() {
                    continue;
                }

                let start_idx = sym.start_line - 1;
                let end_idx = sym.end_line.min(lines.len());
                let body_slice = &lines[start_idx..end_idx];

                for line in body_slice {
                    for word in extract_identifiers(line) {
                        if word != sym.name && known_symbols.contains(word) {
                            graph.add_edge(&sym.name, word);
                        }
                    }
                }
            }
        }

        graph.compute_pagerank(20, 0.85);
        graph
    }

    pub fn compute_pagerank(&mut self, iterations: usize, damping: f64) {
        let n = self.symbols.len();
        if n == 0 {
            return;
        }

        let mut rank: HashMap<String, f64> = HashMap::with_capacity(n);
        let init_val = 1.0 / (n as f64);
        for sym in &self.symbols {
            rank.insert(sym.clone(), init_val);
        }

        let nodes: Vec<String> = self.symbols.iter().cloned().collect();

        for _ in 0..iterations {
            let mut next_rank = HashMap::with_capacity(n);
            let mut dangling_sum = 0.0;

            for node in &nodes {
                let out_degree = self.callees.get(node).map(|v| v.len()).unwrap_or(0);
                if out_degree == 0 {
                    dangling_sum += rank.get(node).copied().unwrap_or(0.0);
                }
            }

            let base_score = ((1.0 - damping) + damping * dangling_sum) / (n as f64);

            for nodes in &nodes {
                let mut incoming_sum = 0.0;
                if let Some(incoming) = self.callers.get(nodes) {
                    for caller in incoming {
                        let caller_out = self.callees.get(caller).map(|v| v.len()).unwrap_or(1);
                        let caller_rank = rank.get(caller).copied().unwrap_or(0.0);
                        incoming_sum += caller_rank / (caller_out as f64);
                    }
                }
                next_rank.insert(nodes.clone(), base_score + damping * incoming_sum);
            }

            rank = next_rank;
        }
        self.pagerank = rank;
    }
    pub fn get_callees(&self, symbol: &str) -> Vec<String> {
        self.callees.get(symbol).cloned().unwrap_or_default()
    }

    pub fn get_callers(&self, symbol: &str) -> Vec<String> {
        self.callers.get(symbol).cloned().unwrap_or_default()
    }

    pub fn get_pagerank(&self, symbol: &str) -> f64 {
        self.pagerank.get(symbol).copied().unwrap_or(0.0)
    }

    pub fn top_symbols(&self, limit: usize) -> Vec<(String, f64)> {
        let mut scores: Vec<(String, f64)> =
            self.pagerank.iter().map(|(k, v)| (k.clone(), *v)).collect();
        scores.sort_by(|a, b| b.1.partial_cmp(&a.1).unwrap_or(std::cmp::Ordering::Equal));
        scores.truncate(limit);
        scores
    }
}

fn extract_identifiers(s: &str) -> Vec<&str> {
    let mut identifiers = Vec::new();
    let bytes = s.as_bytes();
    let mut in_ident = false;
    let mut start = 0;

    for (i, &b) in bytes.iter().enumerate() {
        let is_ident_char = b.is_ascii_alphanumeric() || b == b'_';
        if is_ident_char {
            if !in_ident {
                in_ident = true;
                start = i;
            }
        } else if in_ident {
            in_ident = false;
            if let Ok(ident) = std::str::from_utf8(&bytes[start..i]) {
                identifiers.push(ident);
            }
        }
    }

    if in_ident {
        if let Ok(ident) = std::str::from_utf8(&bytes[start..]) {
            identifiers.push(ident);
        }
    }

    identifiers
}
