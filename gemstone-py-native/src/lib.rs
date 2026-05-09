use libloading::{Library, Symbol};
use pyo3::exceptions::{PyOSError, PyTypeError, PyValueError};
use pyo3::prelude::*;
use pyo3::types::{PyAny, PyList, PyModule};
use pyo3::Bound;
use std::env;
use std::ffi::{c_char, c_double, c_int, c_uint, c_void, CString};
use std::fs;
use std::path::{Path, PathBuf};
use std::sync::{Arc, Mutex, OnceLock};

const OOP_ILLEGAL: u64 = 0x01;
const OOP_NIL: u64 = 0x14;
const OOP_FALSE: u64 = 0x0C;
const OOP_TRUE: u64 = 0x10C;
const OOP_ASCII_NUL: u64 = 0x1C;
const GCI_INVALID_SESSION: u64 = 0;
const GCI_ENCRYPT_BUF_SIZE: u64 = 1024;
const GCI_LOGIN_PW_ENCRYPTED: u64 = 0x1;
const GCI_LOGIN_IS_GCSTS: u64 = 0x2;
const GCI_ERR_STR_SIZE: u64 = 1024;
const GCI_MAX_ERR_ARGS: u64 = 10;

const TAG_SMALLINT: u64 = 0x2;
const TAG_SMALLDOUBLE: u64 = 0x6;
const TAG_SPECIAL: u64 = 0x4;
const SMALLINT_SHIFT: i32 = 3;
const CHAR_TAG_BYTE: u64 = 0x1C;

static LOADED_LIBRARIES: OnceLock<Mutex<Vec<Arc<Library>>>> = OnceLock::new();

#[pyclass]
struct NativeGciLibrary {
    library: Arc<Library>,
    path: PathBuf,
}

#[pymethods]
impl NativeGciLibrary {
    #[getter]
    fn path(&self) -> String {
        self.path.display().to_string()
    }

    #[pyo3(name = "GciInit")]
    fn gci_init(&self, py: Python<'_>) -> PyResult<c_int> {
        let init: Symbol<unsafe extern "C" fn() -> c_int> = self.symbol(b"GciInit")?;
        Ok(py.detach(|| unsafe { init() }))
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
        let set_net: Symbol<
            unsafe extern "C" fn(*const c_char, *const c_char, *const c_char, *const c_char),
        > = self.symbol(b"GciSetNet")?;
        py.detach(|| unsafe {
            set_net(
                stone_nrs.as_ptr(),
                host_username.as_ptr(),
                encrypted_host_password as *const c_char,
                gem_service.as_ptr(),
            )
        });
        Ok(())
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
        let encrypt: Symbol<
            unsafe extern "C" fn(*const c_char, *mut c_char, c_uint) -> *mut c_char,
        > = self.symbol(b"GciEncrypt")?;
        py.detach(|| unsafe {
            encrypt(password.as_ptr(), buffer as *mut c_char, buffer_size);
        });
        Ok(())
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
        let login: Symbol<
            unsafe extern "C" fn(*const c_char, *const c_char, c_uint, c_int) -> c_int,
        > = self.symbol(b"GciLoginEx")?;
        Ok(py.detach(|| unsafe {
            login(username.as_ptr(), password.as_ptr(), flags, halt_on_error)
        }))
    }

    #[pyo3(name = "GciLogout")]
    fn gci_logout(&self, py: Python<'_>) -> PyResult<c_int> {
        let logout: Symbol<unsafe extern "C" fn() -> c_int> = self.symbol(b"GciLogout")?;
        Ok(py.detach(|| unsafe { logout() }))
    }

    #[pyo3(name = "GciCommit")]
    fn gci_commit(&self, py: Python<'_>, err: &Bound<'_, PyAny>) -> PyResult<c_int> {
        let err = ctypes_address(py, err)?;
        let commit: Symbol<unsafe extern "C" fn(*mut c_void) -> c_int> =
            self.symbol(b"GciCommit")?;
        Ok(py.detach(|| unsafe { commit(err as *mut c_void) }))
    }

    #[pyo3(name = "GciAbort")]
    fn gci_abort(&self, py: Python<'_>, err: &Bound<'_, PyAny>) -> PyResult<c_int> {
        let err = ctypes_address(py, err)?;
        let abort: Symbol<unsafe extern "C" fn(*mut c_void) -> c_int> = self.symbol(b"GciAbort")?;
        Ok(py.detach(|| unsafe { abort(err as *mut c_void) }))
    }

    #[pyo3(name = "GciErr")]
    fn gci_err(&self, py: Python<'_>, err: &Bound<'_, PyAny>) -> PyResult<c_int> {
        let err = ctypes_address(py, err)?;
        let gci_err: Symbol<unsafe extern "C" fn(*mut c_void) -> c_int> = self.symbol(b"GciErr")?;
        Ok(py.detach(|| unsafe { gci_err(err as *mut c_void) }))
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
        let execute: Symbol<unsafe extern "C" fn(*const c_char, u64) -> u64> =
            self.symbol(b"GciExecuteStr")?;
        Ok(py.detach(|| unsafe { execute(source.as_ptr(), receiver) }))
    }

    #[pyo3(name = "GciNewString")]
    fn gci_new_string(&self, py: Python<'_>, value: &Bound<'_, PyAny>) -> PyResult<u64> {
        let value = py_cstring(value)?;
        let new_string: Symbol<unsafe extern "C" fn(*const c_char) -> u64> =
            self.symbol(b"GciNewString")?;
        Ok(py.detach(|| unsafe { new_string(value.as_ptr()) }))
    }

    #[pyo3(name = "GciNewSymbol")]
    fn gci_new_symbol(&self, py: Python<'_>, value: &Bound<'_, PyAny>) -> PyResult<u64> {
        let value = py_cstring(value)?;
        let new_symbol: Symbol<unsafe extern "C" fn(*const c_char) -> u64> =
            self.symbol(b"GciNewSymbol")?;
        Ok(py.detach(|| unsafe { new_symbol(value.as_ptr()) }))
    }

    #[pyo3(name = "GciFltToOop")]
    fn gci_flt_to_oop(&self, py: Python<'_>, value: &Bound<'_, PyAny>) -> PyResult<u64> {
        let value = py_f64(value)?;
        let flt_to_oop: Symbol<unsafe extern "C" fn(c_double) -> u64> =
            self.symbol(b"GciFltToOop")?;
        Ok(py.detach(|| unsafe { flt_to_oop(value) }))
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
        let oop_to_flt: Symbol<unsafe extern "C" fn(u64, *mut c_double) -> c_int> =
            self.symbol(b"GciOopToFlt_")?;
        Ok(py.detach(|| unsafe { oop_to_flt(oop, value as *mut c_double) }))
    }

    #[pyo3(name = "GciFetchSize_")]
    fn gci_fetch_size(&self, py: Python<'_>, oop: &Bound<'_, PyAny>) -> PyResult<i64> {
        let oop = py_u64(oop)?;
        let fetch_size: Symbol<unsafe extern "C" fn(u64) -> i64> = self.symbol(b"GciFetchSize_")?;
        Ok(py.detach(|| unsafe { fetch_size(oop) }))
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
        let fetch_bytes: Symbol<unsafe extern "C" fn(u64, i64, *mut c_char, i64) -> i64> =
            self.symbol(b"GciFetchBytes_")?;
        Ok(py.detach(|| unsafe { fetch_bytes(oop, start, buffer as *mut c_char, count) }))
    }

    #[pyo3(name = "GciFetchClass")]
    fn gci_fetch_class(&self, py: Python<'_>, oop: &Bound<'_, PyAny>) -> PyResult<u64> {
        let oop = py_u64(oop)?;
        let fetch_class: Symbol<unsafe extern "C" fn(u64) -> u64> =
            self.symbol(b"GciFetchClass")?;
        Ok(py.detach(|| unsafe { fetch_class(oop) }))
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
        let perform: Symbol<unsafe extern "C" fn(u64, *const c_char, *const u64, c_int) -> u64> =
            self.symbol(b"GciPerform")?;
        Ok(py.detach(|| unsafe { perform(receiver, selector.as_ptr(), args as *const u64, argc) }))
    }

    #[pyo3(name = "GciNewOop")]
    fn gci_new_oop(&self, py: Python<'_>, class_oop: &Bound<'_, PyAny>) -> PyResult<u64> {
        let class_oop = py_u64(class_oop)?;
        let new_oop: Symbol<unsafe extern "C" fn(u64) -> u64> = self.symbol(b"GciNewOop")?;
        Ok(py.detach(|| unsafe { new_oop(class_oop) }))
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
        let resolve: Symbol<unsafe extern "C" fn(*const c_char, u64) -> u64> =
            self.symbol(b"GciResolveSymbol")?;
        Ok(py.detach(|| unsafe { resolve(name.as_ptr(), symbol_list) }))
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
        let sym_dict_at_put: Symbol<unsafe extern "C" fn(u64, *const c_char, u64)> =
            self.symbol(b"GciSymDictAtPut")?;
        py.detach(|| unsafe { sym_dict_at_put(dict, key.as_ptr(), value) });
        Ok(())
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
        let sym_dict_at_obj_put: Symbol<unsafe extern "C" fn(u64, u64, u64)> =
            self.symbol(b"GciSymDictAtObjPut")?;
        py.detach(|| unsafe { sym_dict_at_obj_put(dict, key, value) });
        Ok(())
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
        let at_put: Symbol<unsafe extern "C" fn(u64, *const c_char, u64)> =
            self.symbol(b"GciStrKeyValueDictAtPut")?;
        py.detach(|| unsafe { at_put(dict, key.as_ptr(), value) });
        Ok(())
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
        let at: Symbol<unsafe extern "C" fn(u64, *const c_char, *mut u64)> =
            self.symbol(b"GciStrKeyValueDictAt")?;
        py.detach(|| unsafe { at(dict, key.as_ptr(), value as *mut u64) });
        Ok(())
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
        let at: Symbol<unsafe extern "C" fn(u64, *const c_char, *mut u64, *mut u64)> =
            self.symbol(b"GciSymDictAt")?;
        py.detach(|| unsafe { at(dict, key.as_ptr(), value as *mut u64, assoc as *mut u64) });
        Ok(())
    }

    #[pyo3(name = "GciGetSessionId")]
    fn gci_get_session_id(&self, py: Python<'_>) -> PyResult<c_int> {
        let get_session_id: Symbol<unsafe extern "C" fn() -> c_int> =
            self.symbol(b"GciGetSessionId")?;
        Ok(py.detach(|| unsafe { get_session_id() }))
    }

    #[pyo3(name = "GciSetSessionId")]
    fn gci_set_session_id(&self, py: Python<'_>, session_id: &Bound<'_, PyAny>) -> PyResult<()> {
        let session_id = py_i32(session_id)?;
        let set_session_id: Symbol<unsafe extern "C" fn(c_int)> =
            self.symbol(b"GciSetSessionId")?;
        py.detach(|| unsafe { set_session_id(session_id) });
        Ok(())
    }

    #[pyo3(name = "GciNeedsCommit")]
    fn gci_needs_commit(&self, py: Python<'_>) -> PyResult<c_int> {
        let needs_commit: Symbol<unsafe extern "C" fn() -> c_int> =
            self.symbol(b"GciNeedsCommit")?;
        Ok(py.detach(|| unsafe { needs_commit() }))
    }

    #[pyo3(name = "GciInTransaction")]
    fn gci_in_transaction(&self, py: Python<'_>) -> PyResult<c_int> {
        let in_transaction: Symbol<unsafe extern "C" fn() -> c_int> =
            self.symbol(b"GciInTransaction")?;
        Ok(py.detach(|| unsafe { in_transaction() }))
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
        format!("<NativeGciLibrary path='{}'>", self.path.display())
    }
}

impl NativeGciLibrary {
    fn symbol<T>(&self, name: &[u8]) -> PyResult<Symbol<'_, T>> {
        unsafe { self.library.get(name) }.map_err(|err| {
            PyOSError::new_err(format!(
                "{} not found in {}: {err}",
                String::from_utf8_lossy(name),
                self.path.display()
            ))
        })
    }

    fn call_optional_oop_export(&self, py: Python<'_>, name: &[u8], oop: u64) -> PyResult<()> {
        let symbol = unsafe { self.library.get::<unsafe extern "C" fn(u64)>(name) };
        if let Ok(function) = symbol {
            py.detach(|| unsafe { function(oop) });
        }
        Ok(())
    }
}

#[pyfunction]
fn _is_smallint(oop: u64) -> bool {
    (oop & 0x7) == TAG_SMALLINT
}

#[pyfunction]
fn _is_smalldouble(oop: u64) -> bool {
    (oop & 0x7) == TAG_SMALLDOUBLE
}

#[pyfunction]
fn _smallint_to_python(oop: u64) -> i64 {
    (oop as i64) >> SMALLINT_SHIFT
}

#[pyfunction]
fn _python_to_smallint(value: i64) -> u64 {
    ((value << SMALLINT_SHIFT) as u64) | TAG_SMALLINT
}

#[pyfunction]
fn _is_char(oop: u64) -> bool {
    (oop & 0xFF) == CHAR_TAG_BYTE && (oop & 0x6) == TAG_SPECIAL
}

#[pyfunction]
fn _char_to_python(oop: u64) -> PyResult<String> {
    let codepoint = ((oop >> 8) & 0x1F_FFFF) as u32;
    let ch = char::from_u32(codepoint)
        .ok_or_else(|| PyValueError::new_err(format!("invalid GemStone character OOP {oop}")))?;
    Ok(ch.to_string())
}

#[pyfunction]
fn native_implementation() -> &'static str {
    "pyo3"
}

#[pyfunction]
#[pyo3(signature = (lib_path=None))]
fn gci_init(lib_path: Option<String>) -> PyResult<i32> {
    let path = resolve_library_path(lib_path)?;
    let library = Arc::new(
        unsafe { Library::new(&path) }
            .map_err(|err| PyOSError::new_err(format!("cannot load {}: {err}", path.display())))?,
    );
    let result = unsafe {
        let init: Symbol<unsafe extern "C" fn() -> i32> = library
            .get(b"GciInit")
            .map_err(|err| PyOSError::new_err(format!("GciInit not found: {err}")))?;
        init()
    };
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
    let path = resolve_library_path(lib_path)?;
    let library = Arc::new(
        unsafe { Library::new(&path) }
            .map_err(|err| PyOSError::new_err(format!("cannot load {}: {err}", path.display())))?,
    );
    LOADED_LIBRARIES
        .get_or_init(|| Mutex::new(Vec::new()))
        .lock()
        .map_err(|_| PyOSError::new_err("native GCI library lock is poisoned"))?
        .push(Arc::clone(&library));
    Ok(NativeGciLibrary { library, path })
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

    module.add_function(wrap_pyfunction!(_is_smallint, module)?)?;
    module.add_function(wrap_pyfunction!(_is_smalldouble, module)?)?;
    module.add_function(wrap_pyfunction!(_smallint_to_python, module)?)?;
    module.add_function(wrap_pyfunction!(_python_to_smallint, module)?)?;
    module.add_function(wrap_pyfunction!(_is_char, module)?)?;
    module.add_function(wrap_pyfunction!(_char_to_python, module)?)?;
    module.add_function(wrap_pyfunction!(native_implementation, module)?)?;
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

fn resolve_library_path(lib_path: Option<String>) -> PyResult<PathBuf> {
    if let Some(path) = lib_path {
        return Ok(PathBuf::from(path));
    }
    if let Ok(path) = env::var("GS_LIB_PATH") {
        if !path.is_empty() {
            return Ok(PathBuf::from(path));
        }
    }
    if let Ok(dir) = env::var("GS_LIB") {
        if !dir.is_empty() {
            if let Some(path) = find_gcirpc_in_dir(Path::new(&dir))? {
                return Ok(path);
            }
        }
    }
    if let Ok(gemstone) = env::var("GEMSTONE") {
        if !gemstone.is_empty() {
            let lib_dir = Path::new(&gemstone).join("lib");
            if let Some(path) = find_gcirpc_in_dir(&lib_dir)? {
                return Ok(path);
            }
        }
    }
    Err(PyOSError::new_err(
        "Cannot find libgcirpc. Pass lib_path or set GS_LIB_PATH/GS_LIB/GEMSTONE.",
    ))
}

fn find_gcirpc_in_dir(dir: &Path) -> PyResult<Option<PathBuf>> {
    if !dir.is_dir() {
        return Ok(None);
    }
    let mut candidates = Vec::new();
    for entry in fs::read_dir(dir)
        .map_err(|err| PyOSError::new_err(format!("cannot read {}: {err}", dir.display())))?
    {
        let entry = entry
            .map_err(|err| PyOSError::new_err(format!("cannot read {}: {err}", dir.display())))?;
        let path = entry.path();
        let Some(name) = path.file_name().and_then(|value| value.to_str()) else {
            continue;
        };
        if name.starts_with("libgcirpc")
            && (name.ends_with(".dylib") || name.ends_with(".so") || name.ends_with(".dll"))
        {
            candidates.push(path);
        }
    }
    candidates.sort();
    Ok(candidates.pop())
}
