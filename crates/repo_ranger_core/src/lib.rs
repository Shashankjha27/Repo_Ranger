use pyo3::prelude::*;

pub mod ast;
pub mod cache;
pub mod db;
pub mod merkle;
pub mod tarball;

#[pymodule]
fn repo_ranger_core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add("__version__", env!("CARGO_PKG_VERSION"))?;
    Ok(())
}
