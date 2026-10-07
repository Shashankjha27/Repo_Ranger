use rayon::prelude::*;
use std::cmp::Reverse;
use std::path::Path;
use thiserror::Error;
use tree_sitter::Node;

#[derive(Error, Debug)]
pub enum AstError {
    #[error("Failed to configure Tree-sitter language")]
    LanguageError,
    #[error("Tree-sitter parse returned no syntax tree")]
    ParseError,
    #[error("Invalid UTF-8 source code: {0}")]
    Utf8Error(#[from] std::str::Utf8Error),
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum SupportedLanguage {
    Rust,
    Python,
    TypeScript,
    JavaScript,
    Tsx,
    Go,
    Cpp,
    C,
    Java,
    Unsupported,
}

impl SupportedLanguage {
    pub fn from_path(path: &str) -> Self {
        let ext = Path::new(path)
            .extension()
            .and_then(|e| e.to_str())
            .unwrap_or("");
        match ext {
            "rs" => Self::Rust,
            "py" | "pyi" => Self::Python,
            "ts" | "mts" | "cts" => Self::TypeScript,
            "js" | "mjs" | "cjs" | "jsx" => Self::JavaScript,
            "tsx" => Self::Tsx,
            "go" => Self::Go,
            "cpp" | "cc" | "hpp" | "cxx" | "hxx" => Self::Cpp,
            "c" | "h" => Self::C,
            "java" => Self::Java,
            _ => Self::Unsupported,
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum SymbolKind {
    Function,
    Struct,
    Class,
    Interface,
    Enum,
    Trait,
    Impl,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct CodeSymbol {
    pub name: String,
    pub kind: SymbolKind,
    pub signature: String,
    pub start_line: usize,
    pub end_line: usize,
}

pub struct AstEngine;

impl AstEngine {
    fn get_parser(lang: SupportedLanguage) -> Result<Option<tree_sitter::Parser>, AstError> {
        let language: tree_sitter::Language = match lang {
            SupportedLanguage::Rust => tree_sitter_rust::LANGUAGE.into(),
            SupportedLanguage::Python => tree_sitter_python::LANGUAGE.into(),
            SupportedLanguage::TypeScript => tree_sitter_typescript::LANGUAGE_TYPESCRIPT.into(),
            SupportedLanguage::JavaScript => tree_sitter_javascript::LANGUAGE.into(),
            SupportedLanguage::Tsx => tree_sitter_typescript::LANGUAGE_TSX.into(),
            SupportedLanguage::Go => tree_sitter_go::LANGUAGE.into(),
            SupportedLanguage::Cpp => tree_sitter_cpp::LANGUAGE.into(),
            SupportedLanguage::C => tree_sitter_c::LANGUAGE.into(),
            SupportedLanguage::Java => tree_sitter_java::LANGUAGE.into(),
            SupportedLanguage::Unsupported => return Ok(None),
        };
        let mut parser = tree_sitter::Parser::new();
        parser
            .set_language(&language)
            .map_err(|_| AstError::LanguageError)?;
        Ok(Some(parser))
    }
    fn parse_file<'a>(
        path: &str,
        content: &'a [u8],
    ) -> Result<(&'a str, Option<(tree_sitter::Tree, SupportedLanguage)>), AstError> {
        let source_str = std::str::from_utf8(content)?;
        let lang = SupportedLanguage::from_path(path);

        let Some(mut parser) = Self::get_parser(lang)? else {
            return Ok((source_str, None));
        };

        let tree = parser.parse(source_str, None).ok_or(AstError::ParseError)?;

        Ok((source_str, Some((tree, lang))))
    }

    pub fn compress(path: &str, content: &[u8]) -> Result<String, AstError> {
        let (source_str, parsed) = Self::parse_file(path, content)?;
        let Some((tree, lang)) = parsed else {
            return Ok(source_str.to_string());
        };

        let mut spans = Vec::new();
        collect_function_bodies_for_language(tree.root_node(), lang, &mut spans);
        spans.sort_by_key(|s| (s.0, Reverse(s.1)));

        let mut out = String::with_capacity(source_str.len());
        let mut cursor = 0usize;

        for (start, end, replacement) in spans {
            if start < cursor || start >= end {
                continue;
            }
            let (Some(before), Some(_)) =
                (source_str.get(cursor..start), source_str.get(start..end))
            else {
                continue;
            };
            out.push_str(before);
            out.push_str(&replacement);
            cursor = end;
        }
        out.push_str(&source_str[cursor..]);
        Ok(out)
    }

    pub fn extract_symbols(path: &str, content: &[u8]) -> Result<Vec<CodeSymbol>, AstError> {
        let (source_str, parsed) = Self::parse_file(path, content)?;
        let Some((tree, _lang)) = parsed else {
            return Ok(Vec::new());
        };
        let mut symbols = Vec::new();
        collect_symbols_recursive(tree.root_node(), source_str, &mut symbols);
        Ok(symbols)
    }
}

fn function_spec(lang: SupportedLanguage) -> (&'static [&'static str], &'static str) {
    use SupportedLanguage as L;
    match lang {
        L::Rust => (&["function_item"], "{ ... }"),
        L::Python => (&["function_definition"], "..."),
        L::TypeScript | L::Tsx | L::JavaScript => (
            &[
                "function_declaration",
                "method_definition",
                "arrow_function",
                "function",
            ],
            "{ ... }",
        ),
        L::Go => (&["function_declaration", "method_declaration"], "{ ... }"),
        L::C | L::Cpp => (&["function_definition"], "{ ... }"),
        L::Java => (
            &["method_declaration", "constructor_declaration"],
            "{ ... }",
        ),
        L::Unsupported => (&[], ""),
    }
}

fn collect_function_bodies_for_language(
    node: Node,
    lang: SupportedLanguage,
    spans: &mut Vec<(usize, usize, &'static str)>,
) {
    let (kinds, replacement) = function_spec(lang);

    if kinds.contains(&node.kind()) {
        if let Some(body) = node.child_by_field_name("body") {
            spans.push((body.start_byte(), body.end_byte(), replacement));
            return;
        }
    }

    let mut cursor = node.walk();
    for child in node.children(&mut cursor) {
        collect_function_bodies_for_language(child, lang, spans);
    }
}

fn symbol_kind(kind: &str) -> Option<SymbolKind> {
    Some(match kind {
        "function_item"
        | "function_definition"
        | "function_declaration"
        | "method_declaration"
        | "method_definition" => SymbolKind::Function,
        "struct_item" | "struct_specifier" | "type_spec" => SymbolKind::Struct,
        "class_definition" | "class_declaration" | "class_specifier" => SymbolKind::Class,
        "interface_declaration" => SymbolKind::Interface,
        "enum_item" | "enum_declaration" => SymbolKind::Enum,
        "trait_item" => SymbolKind::Trait,
        "impl_item" => SymbolKind::Impl,
        _ => return None,
    })
}

fn name_node(node: Node) -> Option<Node> {
    if let Some(n) = node.child_by_field_name("name") {
        return Some(n);
    }
    if let Some(d) = node.child_by_field_name("declarator") {
        return name_node(d).or(Some(d));
    }
    node.child_by_field_name("type")
}

fn collect_symbols_recursive(node: Node, source: &str, symbols: &mut Vec<CodeSymbol>) {
    if let Some(kind) = symbol_kind(node.kind()) {
        if let Some(name) = name_node(node).and_then(|n| n.utf8_text(source.as_bytes()).ok()) {
            let sig_end = node
                .child_by_field_name("body")
                .map_or(node.end_byte(), |b| b.start_byte());

            let signature = source
                .get(node.start_byte()..sig_end)
                .map(|s| s.trim())
                .filter(|s| !s.is_empty())
                .unwrap_or(name)
                .to_string();

            symbols.push(CodeSymbol {
                name: name.to_string(),
                kind,
                signature,
                start_line: node.start_position().row + 1,
                end_line: node.end_position().row + 1,
            });
        }
    }

    let mut cursor = node.walk();
    for child in node.children(&mut cursor) {
        collect_symbols_recursive(child, source, symbols);
    }
}

pub fn compress_batch(files: &[(&str, &[u8])]) -> Vec<Result<(String, String), AstError>> {
    files
        .par_iter()
        .map(|&(path, content)| {
            AstEngine::compress(path, content).map(|compressed| (path.to_string(), compressed))
        })
        .collect()
}
