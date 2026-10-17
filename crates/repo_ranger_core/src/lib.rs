use pyo3::prelude::*;
use std::path::PathBuf;
use std::sync::Mutex;

pub mod ast;
pub mod cache;
pub mod db;
pub mod graph;
pub mod merkle;
pub mod tarball;

#[pyclass(get_all, skip_from_py_object)]
#[derive(Clone, Debug, PartialEq)]
pub struct PyTarballStats {
    pub files_processed: usize,
    pub files_skipped_oversized: usize,
    pub bytes_decompressed: u64,
}

#[pyclass(get_all, skip_from_py_object)]
#[derive(Clone, Debug, PartialEq)]
pub struct PyTreeDiff {
    pub added: Vec<String>,
    pub modified: Vec<String>,
    pub removed: Vec<String>,
}

#[pyclass(get_all, skip_from_py_object)]
#[derive(Clone, Debug, PartialEq)]
pub struct PyCodeSymbol {
    pub name: String,
    pub kind: String,
    pub signature: String,
    pub start_line: usize,
    pub end_line: usize,
}

#[pyclass(get_all, skip_from_py_object)]
#[derive(Clone, Debug, PartialEq)]
pub struct PySearchHit {
    pub file_path: String,
    pub snippet: String,
    pub score: f64,
}

#[pyclass]
pub struct PyMerkleTree {
    inner: Mutex<merkle::MerkleTree>,
}

#[pymethods]
impl PyMerkleTree {
    #[new]
    pub fn new() -> Self {
        Self {
            inner: Mutex::new(merkle::MerkleTree::new()),
        }
    }

    pub fn add_file(&self, path: &str, content: &[u8]) {
        self.inner.lock().unwrap().add_file(path, content);
    }

    pub fn root_hash(&self) -> String {
        self.inner.lock().unwrap().root_hash_hex()
    }

    pub fn diff(&self, other: &PyMerkleTree) -> PyTreeDiff {
        let this = self.inner.lock().unwrap();
        let that = other.inner.lock().unwrap();
        let diff = this.diff(&that);
        PyTreeDiff {
            added: diff.added,
            modified: diff.modified,
            removed: diff.removed,
        }
    }

    pub fn __len__(&self) -> usize {
        self.inner.lock().unwrap().len()
    }
}

impl Default for PyMerkleTree {
    fn default() -> Self {
        Self::new()
    }
}

#[pyclass]
pub struct PyCodeDatabase {
    pub(crate) inner: Mutex<db::CodeDatabase>,
}

#[pymethods]
impl PyCodeDatabase {
    #[new]
    pub fn new() -> PyResult<Self> {
        let database = db::CodeDatabase::new_in_memory()
            .map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(e.to_string()))?;
        Ok(Self {
            inner: Mutex::new(database),
        })
    }

    pub fn index(&self, files: Vec<(String, String)>) -> PyResult<()> {
        let indexed_files: Vec<db::IndexedFile> = files
            .into_iter()
            .map(|(path, content)| {
                let symbols =
                    ast::AstEngine::extract_symbols(&path, content.as_bytes()).unwrap_or_default();
                db::IndexedFile {
                    path,
                    content,
                    symbols,
                }
            })
            .collect();

        self.inner
            .lock()
            .unwrap()
            .index(&indexed_files)
            .map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(e.to_string()))
    }

    #[pyo3(signature = (query, limit=None))]
    pub fn search(&self, query: &str, limit: Option<usize>) -> PyResult<Vec<PySearchHit>> {
        let hits = self
            .inner
            .lock()
            .unwrap()
            .search(query, limit.unwrap_or(10))
            .map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(e.to_string()))?;
        Ok(hits
            .into_iter()
            .map(|h| PySearchHit {
                file_path: h.file_path,
                snippet: h.snippet,
                score: h.score,
            })
            .collect())
    }

    pub fn find_symbol(&self, name: &str) -> PyResult<Vec<PyCodeSymbol>> {
        let records = self
            .inner
            .lock()
            .unwrap()
            .find_symbol(name)
            .map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(e.to_string()))?;

        Ok(records
            .into_iter()
            .map(|r| PyCodeSymbol {
                name: r.name,
                kind: format!("{:?}", r.kind),
                signature: r.signature,
                start_line: r.start_line,
                end_line: r.end_line,
            })
            .collect())
    }
}

impl Default for PyCodeDatabase {
    fn default() -> Self {
        Self::new().expect("Failed to initialize in memory DB")
    }
}

#[pyclass]
pub struct PyCacheManager {
    inner: cache::CacheManager,
}

#[pymethods]
impl PyCacheManager {
    #[new]
    #[pyo3(signature = (cache_dir = None, max_size_bytes = None))]
    pub fn new(cache_dir: Option<String>, max_size_bytes: Option<u64>) -> Self {
        let dir = cache_dir
            .map(PathBuf::from)
            .unwrap_or_else(cache::CacheManager::default_dir);
        let max_bytes = max_size_bytes.unwrap_or(cache::DEFAULT_MAX_CACHE_BYTES);
        Self {
            inner: cache::CacheManager::new(dir, max_bytes),
        }
    }

    pub fn save(&self, merkle_root: &str, db: &PyCodeDatabase) -> PyResult<String> {
        let locked_db = db.inner.lock().unwrap();
        let path = self
            .inner
            .save(merkle_root, &locked_db)
            .map_err(|e| pyo3::exceptions::PyIOError::new_err(e.to_string()))?;
        Ok(path.to_string_lossy().to_string())
    }

    pub fn load(&self, merkle_root: &str) -> PyResult<Option<PyCodeDatabase>> {
        let maybe_db = self
            .inner
            .load(merkle_root)
            .map_err(|e| pyo3::exceptions::PyIOError::new_err(e.to_string()))?;
        Ok(maybe_db.map(|d| PyCodeDatabase {
            inner: Mutex::new(d),
        }))
    }

    pub fn has(&self, merkle_root: &str) -> bool {
        self.inner.has(merkle_root)
    }

    pub fn enforce_quota(&self) -> PyResult<u64> {
        self.inner
            .enforce_quota()
            .map_err(|e| pyo3::exceptions::PyIOError::new_err(e.to_string()))
    }
}

#[pyclass]
pub struct PySymbolGraph {
    inner: graph::SymbolGraph,
}

#[pymethods]
impl PySymbolGraph {
    #[staticmethod]
    pub fn build(files: Vec<(String, String)>) -> Self {
        let indexed_files: Vec<db::IndexedFile> = files
            .into_iter()
            .map(|(path, content)| {
                let symbols =
                    ast::AstEngine::extract_symbols(&path, content.as_bytes()).unwrap_or_default();
                db::IndexedFile {
                    path,
                    content,
                    symbols,
                }
            })
            .collect();
        Self {
            inner: graph::SymbolGraph::build(&indexed_files),
        }
    }

    pub fn get_callers(&self, symbols: &str) -> Vec<String> {
        self.inner.get_callers(symbols)
    }

    pub fn get_callees(&self, symbol: &str) -> Vec<String> {
        self.inner.get_callees(symbol)
    }
    pub fn get_pagerank(&self, symbol: &str) -> f64 {
        self.inner.get_pagerank(symbol)
    }
    #[pyo3(signature = (limit=None))]
    pub fn top_symbols(&self, limit: Option<usize>) -> Vec<(String, f64)> {
        self.inner.top_symbols(limit.unwrap_or(10))
    }
    pub fn symbol_count(&self) -> usize {
        self.inner.symbol_count()
    }
    pub fn edge_count(&self) -> usize {
        self.inner.edge_count()
    }
}
#[pyfunction]
pub fn compress_ast(path: &str, content: &[u8]) -> PyResult<String> {
    ast::AstEngine::compress(path, content)
        .map_err(|e| pyo3::exceptions::PyValueError::new_err(e.to_string()))
}
#[pyfunction]
pub fn extract_symbols(path: &str, content: &[u8]) -> PyResult<Vec<PyCodeSymbol>> {
    let symbols = ast::AstEngine::extract_symbols(path, content)
        .map_err(|e| pyo3::exceptions::PyValueError::new_err(e.to_string()))?;
    Ok(symbols
        .into_iter()
        .map(|s| PyCodeSymbol {
            name: s.name,
            kind: format!("{:?}", s.kind),
            signature: s.signature,
            start_line: s.start_line,
            end_line: s.end_line,
        })
        .collect())
}
#[pyfunction]
pub fn stream_tarball(
    py: Python<'_>,
    tar_gz_bytes: &[u8],
    callback: &Bound<'_, PyAny>,
) -> PyResult<PyTarballStats> {
    let stats = tarball::stream_tarball_in_memory(tar_gz_bytes, |path, content| {
        let py_bytes = pyo3::types::PyBytes::new(py, content);
        callback
            .call1((path, py_bytes))
            .map_err(|e| tarball::TarballError::CallbackError(e.to_string()))?;
        Ok(())
    })
    .map_err(|e| pyo3::exceptions::PyValueError::new_err(e.to_string()))?;
    Ok(PyTarballStats {
        files_processed: stats.files_processed,
        files_skipped_oversized: stats.files_skipped_oversized,
        bytes_decompressed: stats.bytes_decompressed,
    })
}
#[pymodule]
fn repo_ranger_core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add("__version__", env!("CARGO_PKG_VERSION"))?;
    m.add_class::<PyTarballStats>()?;
    m.add_class::<PyTreeDiff>()?;
    m.add_class::<PyCodeSymbol>()?;
    m.add_class::<PySearchHit>()?;
    m.add_class::<PyMerkleTree>()?;
    m.add_class::<PyCodeDatabase>()?;
    m.add_class::<PyCacheManager>()?;
    m.add_class::<PySymbolGraph>()?;
    m.add_function(wrap_pyfunction!(compress_ast, m)?)?;
    m.add_function(wrap_pyfunction!(extract_symbols, m)?)?;
    m.add_function(wrap_pyfunction!(stream_tarball, m)?)?;
    Ok(())
}
