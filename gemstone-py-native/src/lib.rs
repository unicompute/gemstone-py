use gemstone_gci::{
    char_from_oop, i64_to_smallint, is_char, is_smalldouble, is_smallint, smallint_to_i64,
    GciLibrary, GCI_ENCRYPT_BUF_SIZE, GCI_ERR_STR_SIZE, GCI_INVALID_SESSION, GCI_LOGIN_IS_GCSTS,
    GCI_LOGIN_PW_ENCRYPTED, GCI_MAX_ERR_ARGS, OOP_ASCII_NUL, OOP_FALSE, OOP_ILLEGAL, OOP_NIL,
    OOP_TRUE,
};
use gemstone_rs::py_native::{
    capabilities, compatibility_report, conformance_report, handoff_report, migration_report,
    samples_report, smoke_dry_run_report, PyNativeErrorInfo, PyNativeSession, PyNativeValue,
};
use pyo3::exceptions::{PyOSError, PyRuntimeError, PyTypeError, PyValueError};
use pyo3::prelude::*;
use pyo3::types::{PyAny, PyList, PyModule};
use pyo3::Bound;
use std::cell::RefCell;
use std::ffi::{c_char, c_double, c_int, c_uint, c_void, CString};
use std::path::PathBuf;
use std::sync::{Mutex, OnceLock};

static LOADED_LIBRARIES: OnceLock<Mutex<Vec<GciLibrary>>> = OnceLock::new();

#[pyclass]
struct NativeGciLibrary {
    library: GciLibrary,
}

#[pymethods]
impl NativeGciLibrary {
    #[getter]
    fn path(&self) -> String {
        self.library.path().display().to_string()
    }

    #[pyo3(name = "GciInit")]
    fn gci_init(&self, py: Python<'_>) -> PyResult<c_int> {
        py.detach(|| unsafe { self.library.gci_init() })
            .map_err(gci_py_err)
    }

    #[pyo3(name = "GciSetNet")]
    fn gci_set_net(
        &self,
        py: Python<'_>,
        stone_nrs: &Bound<'_, PyAny>,
        host_username: &Bound<'_, PyAny>,
        encrypted_host_password: &Bound<'_, PyAny>,
        gem_service: &Bound<'_, PyAny>,
    ) -> PyResult<()> {
        let stone_nrs = py_cstring(stone_nrs)?;
        let host_username = py_cstring(host_username)?;
        let gem_service = py_cstring(gem_service)?;
        let encrypted_host_password = ctypes_address(py, encrypted_host_password)?;
        py.detach(|| unsafe {
            self.library.gci_set_net(
                &stone_nrs,
                &host_username,
                encrypted_host_password as *const c_char,
                &gem_service,
            )
        })
        .map_err(gci_py_err)
    }

    #[pyo3(name = "GciEncrypt")]
    fn gci_encrypt(
        &self,
        py: Python<'_>,
        password: &Bound<'_, PyAny>,
        buffer: &Bound<'_, PyAny>,
        buffer_size: &Bound<'_, PyAny>,
    ) -> PyResult<()> {
        let password = py_cstring(password)?;
        let buffer = ctypes_address(py, buffer)?;
        let buffer_size = py_u32(buffer_size)?;
        py.detach(|| unsafe {
            self.library
                .gci_encrypt(&password, buffer as *mut c_char, buffer_size)
                .map(|_| ())
        })
        .map_err(gci_py_err)
    }

    #[pyo3(name = "GciLoginEx")]
    fn gci_login_ex(
        &self,
        py: Python<'_>,
        username: &Bound<'_, PyAny>,
        password: &Bound<'_, PyAny>,
        flags: &Bound<'_, PyAny>,
        halt_on_error: &Bound<'_, PyAny>,
    ) -> PyResult<c_int> {
        let username = py_cstring(username)?;
        let password = py_cstring(password)?;
        let flags = py_u32(flags)?;
        let halt_on_error = py_i32(halt_on_error)?;
        py.detach(|| unsafe {
            self.library
                .gci_login_ex(&username, &password, flags, halt_on_error)
        })
        .map_err(gci_py_err)
    }

    #[pyo3(name = "GciLogout")]
    fn gci_logout(&self, py: Python<'_>) -> PyResult<c_int> {
        py.detach(|| unsafe { self.library.gci_logout() })
            .map_err(gci_py_err)
    }

    #[pyo3(name = "GciCommit")]
    fn gci_commit(&self, py: Python<'_>, err: &Bound<'_, PyAny>) -> PyResult<c_int> {
        let err = ctypes_address(py, err)?;
        py.detach(|| unsafe { self.library.gci_commit_ptr(err as *mut c_void) })
            .map_err(gci_py_err)
    }

    #[pyo3(name = "GciAbort")]
    fn gci_abort(&self, py: Python<'_>, err: &Bound<'_, PyAny>) -> PyResult<c_int> {
        let err = ctypes_address(py, err)?;
        py.detach(|| unsafe { self.library.gci_abort_ptr(err as *mut c_void) })
            .map_err(gci_py_err)
    }

    #[pyo3(name = "GciErr")]
    fn gci_err(&self, py: Python<'_>, err: &Bound<'_, PyAny>) -> PyResult<c_int> {
        let err = ctypes_address(py, err)?;
        py.detach(|| unsafe { self.library.gci_err_ptr(err as *mut c_void) })
            .map_err(gci_py_err)
    }

    #[pyo3(name = "GciExecuteStr")]
    fn gci_execute_str(
        &self,
        py: Python<'_>,
        source: &Bound<'_, PyAny>,
        receiver: &Bound<'_, PyAny>,
    ) -> PyResult<u64> {
        let source = py_cstring(source)?;
        let receiver = py_u64(receiver)?;
        py.detach(|| unsafe { self.library.gci_execute_str(&source, receiver) })
            .map_err(gci_py_err)
    }

    #[pyo3(name = "GciNewString")]
    fn gci_new_string(&self, py: Python<'_>, value: &Bound<'_, PyAny>) -> PyResult<u64> {
        let value = py_cstring(value)?;
        py.detach(|| unsafe { self.library.gci_new_string(&value) })
            .map_err(gci_py_err)
    }

    #[pyo3(name = "GciNewSymbol")]
    fn gci_new_symbol(&self, py: Python<'_>, value: &Bound<'_, PyAny>) -> PyResult<u64> {
        let value = py_cstring(value)?;
        py.detach(|| unsafe { self.library.gci_new_symbol(&value) })
            .map_err(gci_py_err)
    }

    #[pyo3(name = "GciFltToOop")]
    fn gci_flt_to_oop(&self, py: Python<'_>, value: &Bound<'_, PyAny>) -> PyResult<u64> {
        let value = py_f64(value)?;
        py.detach(|| unsafe { self.library.gci_flt_to_oop(value) })
            .map_err(gci_py_err)
    }

    #[pyo3(name = "GciOopToFlt_")]
    fn gci_oop_to_flt(
        &self,
        py: Python<'_>,
        oop: &Bound<'_, PyAny>,
        value: &Bound<'_, PyAny>,
    ) -> PyResult<c_int> {
        let oop = py_u64(oop)?;
        let value = ctypes_address(py, value)?;
        py.detach(|| unsafe { self.library.gci_oop_to_flt(oop, value as *mut c_double) })
            .map_err(gci_py_err)
    }

    #[pyo3(name = "GciFetchSize_")]
    fn gci_fetch_size(&self, py: Python<'_>, oop: &Bound<'_, PyAny>) -> PyResult<i64> {
        let oop = py_u64(oop)?;
        py.detach(|| unsafe { self.library.gci_fetch_size(oop) })
            .map_err(gci_py_err)
    }

    #[pyo3(name = "GciFetchBytes_")]
    fn gci_fetch_bytes(
        &self,
        py: Python<'_>,
        oop: &Bound<'_, PyAny>,
        start: &Bound<'_, PyAny>,
        buffer: &Bound<'_, PyAny>,
        count: &Bound<'_, PyAny>,
    ) -> PyResult<i64> {
        let oop = py_u64(oop)?;
        let start = py_i64(start)?;
        let buffer = ctypes_address(py, buffer)?;
        let count = py_i64(count)?;
        py.detach(|| unsafe {
            self.library
                .gci_fetch_bytes(oop, start, buffer as *mut c_char, count)
        })
        .map_err(gci_py_err)
    }

    #[pyo3(name = "GciFetchClass")]
    fn gci_fetch_class(&self, py: Python<'_>, oop: &Bound<'_, PyAny>) -> PyResult<u64> {
        let oop = py_u64(oop)?;
        py.detach(|| unsafe { self.library.gci_fetch_class(oop) })
            .map_err(gci_py_err)
    }

    #[pyo3(name = "GciPerform")]
    fn gci_perform(
        &self,
        py: Python<'_>,
        receiver: &Bound<'_, PyAny>,
        selector: &Bound<'_, PyAny>,
        args: &Bound<'_, PyAny>,
        argc: &Bound<'_, PyAny>,
    ) -> PyResult<u64> {
        let receiver = py_u64(receiver)?;
        let selector = py_cstring(selector)?;
        let args = ctypes_address(py, args)?;
        let argc = py_i32(argc)?;
        py.detach(|| unsafe {
            self.library
                .gci_perform(receiver, &selector, args as *const u64, argc)
        })
        .map_err(gci_py_err)
    }

    #[pyo3(name = "GciNewOop")]
    fn gci_new_oop(&self, py: Python<'_>, class_oop: &Bound<'_, PyAny>) -> PyResult<u64> {
        let class_oop = py_u64(class_oop)?;
        py.detach(|| unsafe { self.library.gci_new_oop(class_oop) })
            .map_err(gci_py_err)
    }

    #[pyo3(name = "GciResolveSymbol")]
    fn gci_resolve_symbol(
        &self,
        py: Python<'_>,
        name: &Bound<'_, PyAny>,
        symbol_list: &Bound<'_, PyAny>,
    ) -> PyResult<u64> {
        let name = py_cstring(name)?;
        let symbol_list = py_u64(symbol_list)?;
        py.detach(|| unsafe { self.library.gci_resolve_symbol(&name, symbol_list) })
            .map_err(gci_py_err)
    }

    #[pyo3(name = "GciSymDictAtPut")]
    fn gci_sym_dict_at_put(
        &self,
        py: Python<'_>,
        dict: &Bound<'_, PyAny>,
        key: &Bound<'_, PyAny>,
        value: &Bound<'_, PyAny>,
    ) -> PyResult<()> {
        let dict = py_u64(dict)?;
        let key = py_cstring(key)?;
        let value = py_u64(value)?;
        py.detach(|| unsafe { self.library.gci_sym_dict_at_put(dict, &key, value) })
            .map_err(gci_py_err)
    }

    #[pyo3(name = "GciSymDictAtObjPut")]
    fn gci_sym_dict_at_obj_put(
        &self,
        py: Python<'_>,
        dict: &Bound<'_, PyAny>,
        key: &Bound<'_, PyAny>,
        value: &Bound<'_, PyAny>,
    ) -> PyResult<()> {
        let dict = py_u64(dict)?;
        let key = py_u64(key)?;
        let value = py_u64(value)?;
        py.detach(|| unsafe { self.library.gci_sym_dict_at_obj_put(dict, key, value) })
            .map_err(gci_py_err)
    }

    #[pyo3(name = "GciStrKeyValueDictAtPut")]
    fn gci_str_key_value_dict_at_put(
        &self,
        py: Python<'_>,
        dict: &Bound<'_, PyAny>,
        key: &Bound<'_, PyAny>,
        value: &Bound<'_, PyAny>,
    ) -> PyResult<()> {
        let dict = py_u64(dict)?;
        let key = py_cstring(key)?;
        let value = py_u64(value)?;
        py.detach(|| unsafe {
            self.library
                .gci_str_key_value_dict_at_put(dict, &key, value)
        })
        .map_err(gci_py_err)
    }

    #[pyo3(name = "GciStrKeyValueDictAt")]
    fn gci_str_key_value_dict_at(
        &self,
        py: Python<'_>,
        dict: &Bound<'_, PyAny>,
        key: &Bound<'_, PyAny>,
        value: &Bound<'_, PyAny>,
    ) -> PyResult<()> {
        let dict = py_u64(dict)?;
        let key = py_cstring(key)?;
        let value = ctypes_address(py, value)?;
        py.detach(|| unsafe {
            self.library
                .gci_str_key_value_dict_at(dict, &key, value as *mut u64)
        })
        .map_err(gci_py_err)
    }

    #[pyo3(name = "GciSymDictAt")]
    fn gci_sym_dict_at(
        &self,
        py: Python<'_>,
        dict: &Bound<'_, PyAny>,
        key: &Bound<'_, PyAny>,
        value: &Bound<'_, PyAny>,
        assoc: &Bound<'_, PyAny>,
    ) -> PyResult<()> {
        let dict = py_u64(dict)?;
        let key = py_cstring(key)?;
        let value = ctypes_address(py, value)?;
        let assoc = ctypes_address(py, assoc)?;
        py.detach(|| unsafe {
            self.library
                .gci_sym_dict_at(dict, &key, value as *mut u64, assoc as *mut u64)
        })
        .map_err(gci_py_err)
    }

    #[pyo3(name = "GciGetSessionId")]
    fn gci_get_session_id(&self, py: Python<'_>) -> PyResult<c_int> {
        py.detach(|| unsafe { self.library.gci_get_session_id() })
            .map_err(gci_py_err)
    }

    #[pyo3(name = "GciSetSessionId")]
    fn gci_set_session_id(&self, py: Python<'_>, session_id: &Bound<'_, PyAny>) -> PyResult<()> {
        let session_id = py_i32(session_id)?;
        py.detach(|| unsafe { self.library.gci_set_session_id(session_id) })
            .map_err(gci_py_err)
    }

    #[pyo3(name = "GciNeedsCommit")]
    fn gci_needs_commit(&self, py: Python<'_>) -> PyResult<c_int> {
        py.detach(|| unsafe { self.library.gci_needs_commit() })
            .map_err(gci_py_err)
    }

    #[pyo3(name = "GciInTransaction")]
    fn gci_in_transaction(&self, py: Python<'_>) -> PyResult<c_int> {
        py.detach(|| unsafe { self.library.gci_in_transaction() })
            .map_err(gci_py_err)
    }

    #[pyo3(name = "GciAddOopToExportSet")]
    fn gci_add_oop_to_export_set(&self, py: Python<'_>, oop: &Bound<'_, PyAny>) -> PyResult<()> {
        self.call_optional_oop_export(py, b"GciAddOopToExportSet", py_u64(oop)?)
    }

    #[pyo3(name = "GciRemoveOopFromExportSet")]
    fn gci_remove_oop_from_export_set(
        &self,
        py: Python<'_>,
        oop: &Bound<'_, PyAny>,
    ) -> PyResult<()> {
        self.call_optional_oop_export(py, b"GciRemoveOopFromExportSet", py_u64(oop)?)
    }

    #[pyo3(name = "GciAddObjToExportSet")]
    fn gci_add_obj_to_export_set(&self, py: Python<'_>, oop: &Bound<'_, PyAny>) -> PyResult<()> {
        self.call_optional_oop_export(py, b"GciAddObjToExportSet", py_u64(oop)?)
    }

    #[pyo3(name = "GciRemoveObjFromExportSet")]
    fn gci_remove_obj_from_export_set(
        &self,
        py: Python<'_>,
        oop: &Bound<'_, PyAny>,
    ) -> PyResult<()> {
        self.call_optional_oop_export(py, b"GciRemoveObjFromExportSet", py_u64(oop)?)
    }

    fn __repr__(&self) -> String {
        format!(
            "<NativeGciLibrary path='{}'>",
            self.library.path().display()
        )
    }
}

impl NativeGciLibrary {
    fn call_optional_oop_export(&self, py: Python<'_>, name: &[u8], oop: u64) -> PyResult<()> {
        py.detach(|| unsafe { self.library.call_optional_oop_export(name, oop) })
            .map(|_| ())
            .map_err(gci_py_err)
    }
}

#[pyclass(unsendable)]
struct RustCoreSession {
    inner: RefCell<Option<PyNativeSession>>,
}

#[pymethods]
impl RustCoreSession {
    #[staticmethod]
    fn login_from_env() -> PyResult<Self> {
        Ok(Self {
            inner: RefCell::new(Some(
                PyNativeSession::login_from_env().map_err(rust_core_py_err)?,
            )),
        })
    }

    fn session_id(&self) -> PyResult<i32> {
        with_rust_core_session(&self.inner, |session| Ok(session.session_id()))
    }

    fn eval_repr(&self, source: &str) -> PyResult<String> {
        with_rust_core_session(&self.inner, |session| {
            session
                .eval(source)
                .map(|value| format!("{value:?}"))
                .map_err(rust_core_py_err)
        })
    }

    fn eval_json(&self, source: &str) -> PyResult<String> {
        with_rust_core_session(&self.inner, |session| {
            session
                .eval(source)
                .map(|value| value.to_json())
                .map_err(rust_core_py_err)
        })
    }

    fn eval_smallint(&self, source: &str) -> PyResult<i64> {
        with_rust_core_session(&self.inner, |session| match session.eval(source) {
            Ok(PyNativeValue::SmallInt(value)) => Ok(value),
            Ok(other) => Err(PyValueError::new_err(format!(
                "expected SmallInt from eval, got {other:?}"
            ))),
            Err(error) => Err(rust_core_py_err(error)),
        })
    }

    fn eval_oop(&self, source: &str) -> PyResult<u64> {
        with_rust_core_session(&self.inner, |session| {
            session.eval_oop(source).map_err(rust_core_py_err)
        })
    }

    fn execute(&self, source: &str) -> PyResult<u64> {
        with_rust_core_session(&self.inner, |session| {
            session.execute(source).map_err(rust_core_py_err)
        })
    }

    fn resolve(&self, name: &str) -> PyResult<u64> {
        with_rust_core_session(&self.inner, |session| {
            session.resolve(name).map_err(rust_core_py_err)
        })
    }

    fn value_to_oop_nil(&self) -> PyResult<u64> {
        with_rust_core_session(&self.inner, |session| {
            session
                .value_to_oop(PyNativeValue::Nil)
                .map_err(rust_core_py_err)
        })
    }

    fn value_to_oop_bool(&self, value: bool) -> PyResult<u64> {
        with_rust_core_session(&self.inner, |session| {
            session
                .value_to_oop(PyNativeValue::Bool(value))
                .map_err(rust_core_py_err)
        })
    }

    fn value_to_oop_smallint(&self, value: i64) -> PyResult<u64> {
        with_rust_core_session(&self.inner, |session| {
            session
                .value_to_oop(PyNativeValue::SmallInt(value))
                .map_err(rust_core_py_err)
        })
    }

    fn value_to_oop_char(&self, value: &str) -> PyResult<u64> {
        let mut chars = value.chars();
        let ch = chars
            .next()
            .ok_or_else(|| PyValueError::new_err("expected exactly one character"))?;
        if chars.next().is_some() {
            return Err(PyValueError::new_err("expected exactly one character"));
        }
        with_rust_core_session(&self.inner, |session| {
            session
                .value_to_oop(PyNativeValue::Char(ch))
                .map_err(rust_core_py_err)
        })
    }

    fn value_to_oop_string(&self, value: &str) -> PyResult<u64> {
        with_rust_core_session(&self.inner, |session| {
            session
                .value_to_oop(PyNativeValue::String(value.to_string()))
                .map_err(rust_core_py_err)
        })
    }

    fn value_to_oop_symbol(&self, value: &str) -> PyResult<u64> {
        with_rust_core_session(&self.inner, |session| {
            session
                .value_to_oop(PyNativeValue::Symbol(value.to_string()))
                .map_err(rust_core_py_err)
        })
    }

    fn value_to_oop_raw(&self, value: u64) -> PyResult<u64> {
        with_rust_core_session(&self.inner, |session| {
            session
                .value_to_oop(PyNativeValue::Oop(value))
                .map_err(rust_core_py_err)
        })
    }

    fn perform_raw_oop(&self, receiver: u64, selector: &str, args: Vec<u64>) -> PyResult<u64> {
        with_rust_core_session(&self.inner, |session| {
            session
                .perform_oop_raw(receiver, selector, &args)
                .map_err(rust_core_py_err)
        })
    }

    fn perform_json(&self, receiver: u64, selector: &str, args: Vec<u64>) -> PyResult<String> {
        with_rust_core_session(&self.inner, |session| {
            session
                .perform_raw(receiver, selector, &args)
                .map(|value| value.to_json())
                .map_err(rust_core_py_err)
        })
    }

    fn new_string(&self, value: &str) -> PyResult<u64> {
        with_rust_core_session(&self.inner, |session| {
            session.new_string(value).map_err(rust_core_py_err)
        })
    }

    fn new_symbol(&self, value: &str) -> PyResult<u64> {
        with_rust_core_session(&self.inner, |session| {
            session.new_symbol(value).map_err(rust_core_py_err)
        })
    }

    fn fetch_string(&self, oop: u64) -> PyResult<String> {
        with_rust_core_session(&self.inner, |session| {
            session.fetch_string(oop).map_err(rust_core_py_err)
        })
    }

    fn global_get(&self, symbol_name: &str) -> PyResult<u64> {
        with_rust_core_session(&self.inner, |session| {
            session.global_get(symbol_name).map_err(rust_core_py_err)
        })
    }

    fn global_put_raw(&self, symbol_name: &str, value: u64) -> PyResult<()> {
        with_rust_core_session(&self.inner, |session| {
            session
                .global_put_raw(symbol_name, value)
                .map_err(rust_core_py_err)
        })
    }

    fn global_put_string(&self, symbol_name: &str, value: &str) -> PyResult<()> {
        with_rust_core_session(&self.inner, |session| {
            session
                .global_put_value(symbol_name, PyNativeValue::String(value.to_string()))
                .map_err(rust_core_py_err)
        })
    }

    fn global_put_smallint(&self, symbol_name: &str, value: i64) -> PyResult<()> {
        with_rust_core_session(&self.inner, |session| {
            session
                .global_put_value(symbol_name, PyNativeValue::SmallInt(value))
                .map_err(rust_core_py_err)
        })
    }

    fn add_to_export_set(&self, oop: u64) -> PyResult<()> {
        with_rust_core_session(&self.inner, |session| {
            session.add_to_export_set(oop).map_err(rust_core_py_err)
        })
    }

    fn remove_from_export_set(&self, oop: u64) -> PyResult<()> {
        with_rust_core_session(&self.inner, |session| {
            session
                .remove_from_export_set(oop)
                .map_err(rust_core_py_err)
        })
    }

    fn needs_commit(&self) -> PyResult<bool> {
        with_rust_core_session(&self.inner, |session| {
            session.needs_commit().map_err(rust_core_py_err)
        })
    }

    fn in_transaction(&self) -> PyResult<bool> {
        with_rust_core_session(&self.inner, |session| {
            session.in_transaction().map_err(rust_core_py_err)
        })
    }

    fn commit(&self) -> PyResult<()> {
        with_rust_core_session(&self.inner, |session| {
            session.commit().map_err(rust_core_py_err)
        })
    }

    fn abort(&self) -> PyResult<()> {
        with_rust_core_session(&self.inner, |session| {
            session.abort().map_err(rust_core_py_err)
        })
    }

    fn logout(&self) -> PyResult<()> {
        if let Some(mut session) = self.inner.borrow_mut().take() {
            session.logout().map_err(rust_core_py_err)?;
        }
        Ok(())
    }
}

impl Drop for RustCoreSession {
    fn drop(&mut self) {
        if let Some(mut session) = self.inner.borrow_mut().take() {
            let _ = session.logout();
        }
    }
}

#[pyfunction]
fn _is_smallint(oop: u64) -> bool {
    is_smallint(oop)
}

#[pyfunction]
fn _is_smalldouble(oop: u64) -> bool {
    is_smalldouble(oop)
}

#[pyfunction]
fn _smallint_to_python(oop: u64) -> i64 {
    smallint_to_i64(oop)
}

#[pyfunction]
fn _python_to_smallint(value: i64) -> u64 {
    i64_to_smallint(value)
}

#[pyfunction]
fn _is_char(oop: u64) -> bool {
    is_char(oop)
}

#[pyfunction]
fn _char_to_python(oop: u64) -> PyResult<String> {
    char_from_oop(oop)
        .map(|ch| ch.to_string())
        .map_err(|err| PyValueError::new_err(err.to_string()))
}

#[pyfunction]
fn native_implementation() -> &'static str {
    "pyo3"
}

#[pyfunction]
fn rust_core_implementation() -> &'static str {
    "gemstone-rs"
}

#[pyfunction]
fn rust_core_capabilities_json() -> String {
    capabilities().to_json()
}

#[pyfunction]
fn rust_core_samples_json() -> String {
    samples_report().to_json()
}

#[pyfunction]
fn rust_core_smoke_dry_run_json() -> String {
    smoke_dry_run_report().to_json()
}

#[pyfunction]
fn rust_core_migration_json() -> String {
    migration_report().to_json()
}

#[pyfunction]
fn rust_core_compatibility_json() -> String {
    compatibility_report().to_json()
}

#[pyfunction]
fn rust_core_conformance_json() -> String {
    conformance_report().to_json()
}

#[pyfunction]
fn rust_core_handoff_json() -> String {
    handoff_report().to_json()
}

#[pyfunction]
#[pyo3(signature = (lib_path=None))]
fn gci_init(lib_path: Option<String>) -> PyResult<i32> {
    let library = GciLibrary::load(lib_path.map(PathBuf::from)).map_err(gci_py_err)?;
    let result = unsafe { library.gci_init() }.map_err(gci_py_err)?;
    LOADED_LIBRARIES
        .get_or_init(|| Mutex::new(Vec::new()))
        .lock()
        .map_err(|_| PyOSError::new_err("native GCI library lock is poisoned"))?
        .push(library);
    Ok(result)
}

#[pyfunction]
#[pyo3(signature = (lib_path=None))]
fn _load_library(lib_path: Option<String>) -> PyResult<NativeGciLibrary> {
    let library = GciLibrary::load(lib_path.map(PathBuf::from)).map_err(gci_py_err)?;
    LOADED_LIBRARIES
        .get_or_init(|| Mutex::new(Vec::new()))
        .lock()
        .map_err(|_| PyOSError::new_err("native GCI library lock is poisoned"))?
        .push(library.clone());
    Ok(NativeGciLibrary { library })
}

#[pyfunction]
fn _bind(_library: &Bound<'_, PyAny>) {
    // NativeGciLibrary methods already carry their Rust signatures, so the
    // ctypes-style binding step remains a compatibility no-op.
}

#[pymodule]
fn _gci(py: Python<'_>, module: &Bound<'_, PyModule>) -> PyResult<()> {
    copy_ctypes_fallback_surface(py, module)?;

    module.add("OOP_ILLEGAL", OOP_ILLEGAL)?;
    module.add("OOP_NIL", OOP_NIL)?;
    module.add("OOP_FALSE", OOP_FALSE)?;
    module.add("OOP_TRUE", OOP_TRUE)?;
    module.add("OOP_ASCII_NUL", OOP_ASCII_NUL)?;
    module.add("GCI_ERR_STR_SIZE", GCI_ERR_STR_SIZE)?;
    module.add("GCI_MAX_ERR_ARGS", GCI_MAX_ERR_ARGS)?;
    module.add("GCI_INVALID_SESSION", GCI_INVALID_SESSION)?;
    module.add("GCI_ENCRYPT_BUF_SIZE", GCI_ENCRYPT_BUF_SIZE)?;
    module.add("GCI_LOGIN_PW_ENCRYPTED", GCI_LOGIN_PW_ENCRYPTED)?;
    module.add("GCI_LOGIN_IS_GCSTS", GCI_LOGIN_IS_GCSTS)?;
    module.add("IMPLEMENTATION", "native")?;
    module.add_class::<NativeGciLibrary>()?;
    module.add_class::<RustCoreSession>()?;

    module.add_function(wrap_pyfunction!(_is_smallint, module)?)?;
    module.add_function(wrap_pyfunction!(_is_smalldouble, module)?)?;
    module.add_function(wrap_pyfunction!(_smallint_to_python, module)?)?;
    module.add_function(wrap_pyfunction!(_python_to_smallint, module)?)?;
    module.add_function(wrap_pyfunction!(_is_char, module)?)?;
    module.add_function(wrap_pyfunction!(_char_to_python, module)?)?;
    module.add_function(wrap_pyfunction!(native_implementation, module)?)?;
    module.add_function(wrap_pyfunction!(rust_core_implementation, module)?)?;
    module.add_function(wrap_pyfunction!(rust_core_capabilities_json, module)?)?;
    module.add_function(wrap_pyfunction!(rust_core_samples_json, module)?)?;
    module.add_function(wrap_pyfunction!(rust_core_smoke_dry_run_json, module)?)?;
    module.add_function(wrap_pyfunction!(rust_core_migration_json, module)?)?;
    module.add_function(wrap_pyfunction!(rust_core_compatibility_json, module)?)?;
    module.add_function(wrap_pyfunction!(rust_core_conformance_json, module)?)?;
    module.add_function(wrap_pyfunction!(rust_core_handoff_json, module)?)?;
    module.add_function(wrap_pyfunction!(gci_init, module)?)?;
    module.add_function(wrap_pyfunction!(_load_library, module)?)?;
    module.add_function(wrap_pyfunction!(_bind, module)?)?;

    let exports = PyList::new(
        py,
        [
            "OOP_ILLEGAL",
            "OOP_NIL",
            "OOP_FALSE",
            "OOP_TRUE",
            "OOP_ASCII_NUL",
            "GCI_ERR_STR_SIZE",
            "GCI_MAX_ERR_ARGS",
            "GCI_INVALID_SESSION",
            "GCI_ENCRYPT_BUF_SIZE",
            "GCI_LOGIN_PW_ENCRYPTED",
            "GCI_LOGIN_IS_GCSTS",
            "GciErrSType",
            "NativeGciLibrary",
            "RustCoreSession",
            "_is_smallint",
            "_is_smalldouble",
            "_smallint_to_python",
            "_python_to_smallint",
            "_is_char",
            "_char_to_python",
            "_load_library",
            "_bind",
            "gci_init",
            "native_implementation",
            "rust_core_implementation",
            "rust_core_capabilities_json",
            "rust_core_samples_json",
            "rust_core_smoke_dry_run_json",
            "rust_core_migration_json",
            "rust_core_compatibility_json",
            "rust_core_conformance_json",
            "rust_core_handoff_json",
        ],
    )?;
    module.add("__all__", exports)?;
    Ok(())
}

fn copy_ctypes_fallback_surface(py: Python<'_>, module: &Bound<'_, PyModule>) -> PyResult<()> {
    let fallback = PyModule::import(py, "gemstone_py._gci_ctypes")?;
    for name in ["GciErrSType"] {
        module.add(name, fallback.getattr(name)?)?;
    }
    Ok(())
}

fn py_u64(value: &Bound<'_, PyAny>) -> PyResult<u64> {
    if let Ok(number) = value.extract::<u64>() {
        return Ok(number);
    }
    if let Ok(inner) = value.getattr("value") {
        return py_u64(&inner);
    }
    Err(PyTypeError::new_err("expected an integer-compatible value"))
}

fn py_i64(value: &Bound<'_, PyAny>) -> PyResult<i64> {
    if let Ok(number) = value.extract::<i64>() {
        return Ok(number);
    }
    if let Ok(inner) = value.getattr("value") {
        return py_i64(&inner);
    }
    Err(PyTypeError::new_err("expected an integer-compatible value"))
}

fn py_i32(value: &Bound<'_, PyAny>) -> PyResult<c_int> {
    let number = py_i64(value)?;
    c_int::try_from(number).map_err(|_| PyValueError::new_err("integer does not fit in c_int"))
}

fn py_u32(value: &Bound<'_, PyAny>) -> PyResult<c_uint> {
    let number = py_u64(value)?;
    c_uint::try_from(number).map_err(|_| PyValueError::new_err("integer does not fit in c_uint"))
}

fn py_f64(value: &Bound<'_, PyAny>) -> PyResult<c_double> {
    if let Ok(number) = value.extract::<c_double>() {
        return Ok(number);
    }
    if let Ok(inner) = value.getattr("value") {
        return py_f64(&inner);
    }
    Err(PyTypeError::new_err("expected a float-compatible value"))
}

fn py_cstring(value: &Bound<'_, PyAny>) -> PyResult<CString> {
    if let Ok(bytes) = value.extract::<Vec<u8>>() {
        return CString::new(bytes).map_err(|_| PyValueError::new_err("string contains NUL byte"));
    }
    if let Ok(text) = value.extract::<String>() {
        return CString::new(text).map_err(|_| PyValueError::new_err("string contains NUL byte"));
    }
    if let Ok(inner) = value.getattr("value") {
        return py_cstring(&inner);
    }
    Err(PyTypeError::new_err(
        "expected bytes, str, or ctypes string value",
    ))
}

fn ctypes_address(py: Python<'_>, value: &Bound<'_, PyAny>) -> PyResult<usize> {
    let target = value
        .getattr("_obj")
        .unwrap_or_else(|_| value.clone().into_any());
    let ctypes = PyModule::import(py, "ctypes")?;
    ctypes.getattr("addressof")?.call1((target,))?.extract()
}

fn gci_py_err(err: gemstone_gci::GciError) -> PyErr {
    PyOSError::new_err(err.to_string())
}

fn with_rust_core_session<T>(
    inner: &RefCell<Option<PyNativeSession>>,
    f: impl FnOnce(&mut PyNativeSession) -> PyResult<T>,
) -> PyResult<T> {
    let mut guard = inner.borrow_mut();
    let session = guard
        .as_mut()
        .ok_or_else(|| PyRuntimeError::new_err("GemStone session is logged out"))?;
    f(session)
}

fn rust_core_py_err(error: gemstone_rs::Error) -> PyErr {
    let info = PyNativeErrorInfo::from_error(&error);
    PyRuntimeError::new_err(format!("{:?}: {}", info.kind, info.message))
}
