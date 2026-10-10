use crate::ast::{CodeSymbol, SymbolKind};
use rusqlite::{params, Connection, Result};
use thiserror::Error;

#[derive(Error, Debug)]
pub enum DbError {
    #[error("SQLite database error: {0}")]
    SQLite(#[from] rusqlite::Error),
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct IndexedFile {
    pub path: String,
    pub content: String,
    pub symbols: Vec<CodeSymbol>,
}

#[derive(Debug, Clone, PartialEq)]
pub struct SearchHit {
    pub file_path: String,
    pub snippet: String,
    pub score: f64,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct SymbolRecord {
    pub file_path: String,
    pub name: String,
    pub kind: SymbolKind,
    pub signature: String,
    pub start_line: usize,
    pub end_line: usize,
}

pub struct CodeDatabase {
    conn: Connection,
}

impl CodeDatabase {
    pub fn new_in_memory() -> Result<Self, DbError> {
        let conn = Connection::open_in_memory()?;

        conn.execute_batch(
            "CREATE TABLE symbols (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_path TEXT NOT NULL,
                name TEXT NOT NULL,
                kind TEXT NOT NULL,
                signature TEXT NOT NULL,
                start_line INTEGER NOT NULL,
                end_line INTEGER NOT NULL
            );
            CREATE INDEX idx_symbols_name ON symbols(name);

            CREATE VIRTUAL TABLE fts_code USING fts5(
                file_path,
                content,
                tokenize = \"unicode61 tokenchars '_$'\"
            );",
        )?;

        Ok(Self { conn })
    }

    pub fn index(&mut self, files: &[IndexedFile]) -> Result<(), DbError> {
        let tx = self.conn.transaction()?;
        {
            let mut fts_stmt =
                tx.prepare_cached("INSERT INTO fts_code (file_path, content) VALUES (?1, ?2)")?;
            let mut sym_stmt = tx.prepare_cached(
                "INSERT INTO symbols (file_path, name, kind, signature, start_line, end_line) \
                VALUES (?1, ?2, ?3, ?4, ?5, ?6)",
            )?;

            for file in files {
                fts_stmt.execute(params![file.path, file.content])?;
                for sym in &file.symbols {
                    sym_stmt.execute(params![
                        file.path,
                        sym.name,
                        format!("{:?}", sym.kind),
                        sym.signature,
                        sym.start_line as i64,
                        sym.end_line as i64,
                    ])?;
                }
            }
        }
        tx.commit()?;
        Ok(())
    }

    pub fn search(&self, query: &str, limit: usize) -> Result<Vec<SearchHit>, DbError> {
        let sanitized = sanitize_query(query);
        if sanitized.is_empty() {
            return Ok(Vec::new());
        }

        let mut stmt = self.conn.prepare_cached(
            "SELECT file_path, snippet(fts_code, -1, '<b>', '</b>', '...', 10), bm25(fts_code) \
            FROM fts_code \
            WHERE fts_code MATCH ?1 \
            ORDER BY bm25(fts_code) \
            LIMIT ?2",
        )?;

        let rows = stmt.query_map(params![sanitized, limit as i64], |row| {
            Ok(SearchHit {
                file_path: row.get(0)?,
                snippet: row.get(1)?,
                score: row.get(2)?,
            })
        })?;

        let mut hits = Vec::new();
        for hit in rows {
            hits.push(hit?);
        }
        Ok(hits)
    }

    pub fn find_symbol(&self, name: &str) -> Result<Vec<SymbolRecord>, DbError> {
        let mut stmt = self.conn.prepare_cached(
            "SELECT file_path, name, kind, signature, start_line, end_line \
            FROM symbols \
            WHERE name = ?1",
        )?;

        let rows = stmt.query_map(params![name], |row| {
            let kind_str: String = row.get(2)?;
            Ok(SymbolRecord {
                file_path: row.get(0)?,
                name: row.get(1)?,
                kind: parse_symbol_kind(&kind_str),
                signature: row.get(3)?,
                start_line: row.get::<_, i64>(4)? as usize,
                end_line: row.get::<_, i64>(5)? as usize,
            })
        })?;

        let mut records = Vec::new();
        for rec in rows {
            records.push(rec?);
        }
        Ok(records)
    }

    pub fn conn(&self) -> &Connection {
        &self.conn
    }

    pub fn conn_mut(&mut self) -> &mut Connection {
        &mut self.conn
    }

    pub fn from_connection(connn: Connection) -> Self {
        Self { conn }
    }
}

fn sanitize_query(query: &str) -> String {
    let terms: Vec<String> = query
        .split_whitespace()
        .filter(|w| !w.is_empty())
        .map(|term| {
            let escaped = term.replace('"', "\"\"");
            format!("\"{}\"", escaped)
        })
        .collect();
    terms.join(" ")
}

fn parse_symbol_kind(s: &str) -> SymbolKind {
    match s {
        "Function" => SymbolKind::Function,
        "Struct" => SymbolKind::Struct,
        "Class" => SymbolKind::Class,
        "Interface" => SymbolKind::Interface,
        "Enum" => SymbolKind::Enum,
        "Trait" => SymbolKind::Trait,
        "Impl" => SymbolKind::Impl,
        _ => SymbolKind::Function,
    }
}
