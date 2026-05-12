//! Low-level GemStone/S GCI dynamic loader and raw ABI bindings.
//!
//! This crate intentionally does not require GemStone headers at build time.
//! It loads `libgcirpc` at runtime and keeps all unsafe C ABI calls in one
//! small layer that higher-level Rust and PyO3 crates can share.

use libloading::{Library, Symbol};
use std::env;
use std::error::Error as StdError;
use std::ffi::{c_char, c_double, c_int, c_uint, c_void, CStr};
use std::fmt;
use std::fs;
use std::path::{Path, PathBuf};
use std::sync::Arc;

pub type RawOop = u64;
pub type Result<T> = std::result::Result<T, GciError>;

pub const OOP_ILLEGAL: RawOop = 0x01;
pub const OOP_NIL: RawOop = 0x14;
pub const OOP_FALSE: RawOop = 0x0C;
pub const OOP_TRUE: RawOop = 0x10C;
pub const OOP_ASCII_NUL: RawOop = 0x1C;
pub const GCI_INVALID_SESSION: RawOop = 0;
pub const GCI_ENCRYPT_BUF_SIZE: usize = 1024;
pub const GCI_LOGIN_PW_ENCRYPTED: RawOop = 0x1;
pub const GCI_LOGIN_IS_GCSTS: RawOop = 0x2;
pub const GCI_ERR_STR_SIZE: usize = 1024;
pub const GCI_MAX_ERR_ARGS: usize = 10;

const TAG_SMALLINT: RawOop = 0x2;
const TAG_SMALLDOUBLE: RawOop = 0x6;
const TAG_SPECIAL: RawOop = 0x4;
const SMALLINT_SHIFT: u32 = 3;
const CHAR_TAG_BYTE: RawOop = 0x1C;

#[derive(Clone, Copy, Debug, Eq, PartialEq, Hash)]
pub struct Oop(pub RawOop);

impl Oop {
    pub const ILLEGAL: Self = Self(OOP_ILLEGAL);
    pub const NIL: Self = Self(OOP_NIL);
    pub const FALSE: Self = Self(OOP_FALSE);
    pub const TRUE: Self = Self(OOP_TRUE);

    pub fn from_smallint(value: i64) -> Self {
        Self(i64_to_smallint(value))
    }

    pub fn from_bool(value: bool) -> Self {
        if value {
            Self::TRUE
        } else {
            Self::FALSE
        }
    }

    pub fn from_char(value: char) -> Self {
        Self(char_to_oop(value))
    }

    pub fn raw(self) -> RawOop {
        self.0
    }

    pub fn is_illegal(self) -> bool {
        self.0 == OOP_ILLEGAL
    }

    pub fn is_nil(self) -> bool {
        self.0 == OOP_NIL
    }

    pub fn is_boolean(self) -> bool {
        matches!(self.0, OOP_TRUE | OOP_FALSE)
    }

    pub fn as_bool(self) -> Option<bool> {
        match self.0 {
            OOP_TRUE => Some(true),
            OOP_FALSE => Some(false),
            _ => None,
        }
    }

    pub fn is_smallint(self) -> bool {
        is_smallint(self.0)
    }

    pub fn as_smallint(self) -> Option<i64> {
        self.is_smallint().then(|| smallint_to_i64(self.0))
    }

    pub fn is_char(self) -> bool {
        is_char(self.0)
    }

    pub fn as_char(self) -> Result<Option<char>> {
        if self.is_char() {
            char_from_oop(self.0).map(Some)
        } else {
            Ok(None)
        }
    }
}

impl From<RawOop> for Oop {
    fn from(value: RawOop) -> Self {
        Self(value)
    }
}

impl From<Oop> for RawOop {
    fn from(value: Oop) -> Self {
        value.0
    }
}

#[repr(C)]
#[derive(Clone, Copy)]
pub struct GciErrSType {
    pub category: RawOop,
    pub context: RawOop,
    pub exception_obj: RawOop,
    pub args: [RawOop; GCI_MAX_ERR_ARGS],
    pub number: c_int,
    pub arg_count: c_int,
    pub fatal: u8,
    pub message: [c_char; GCI_ERR_STR_SIZE + 1],
    pub reason: [c_char; GCI_ERR_STR_SIZE + 1],
}

impl Default for GciErrSType {
    fn default() -> Self {
        // SAFETY: GciErrSType is a plain C layout buffer. The all-zero state is
        // the same initialization pattern used by ctypes before GciErr fills it.
        unsafe { std::mem::zeroed() }
    }
}

impl GciErrSType {
    pub fn message_text(&self) -> String {
        c_char_array_to_string(&self.message)
    }

    pub fn reason_text(&self) -> String {
        c_char_array_to_string(&self.reason)
    }

    pub fn full_message(&self) -> String {
        let message = self.message_text();
        let reason = self.reason_text();
        if reason.is_empty() || reason == message {
            message
        } else {
            format!("{message} [{reason}]")
        }
    }
}

#[derive(Debug)]
pub enum GciError {
    LibraryNotFound,
    LibraryLoad {
        path: PathBuf,
        source: libloading::Error,
    },
    Symbol {
        path: PathBuf,
        symbol: String,
        source: libloading::Error,
    },
    ReadDir {
        path: PathBuf,
        source: std::io::Error,
    },
    InvalidCharOop(RawOop),
}

impl fmt::Display for GciError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::LibraryNotFound => write!(
                f,
                "Cannot find libgcirpc. Pass a library path or set GS_LIB_PATH/GS_LIB/GEMSTONE."
            ),
            Self::LibraryLoad { path, source } => {
                write!(f, "cannot load {}: {source}", path.display())
            }
            Self::Symbol {
                path,
                symbol,
                source,
            } => write!(f, "{symbol} not found in {}: {source}", path.display()),
            Self::ReadDir { path, source } => {
                write!(f, "cannot read {}: {source}", path.display())
            }
            Self::InvalidCharOop(oop) => write!(f, "invalid GemStone character OOP {oop}"),
        }
    }
}

impl StdError for GciError {
    fn source(&self) -> Option<&(dyn StdError + 'static)> {
        match self {
            Self::LibraryLoad { source, .. } => Some(source),
            Self::Symbol { source, .. } => Some(source),
            Self::ReadDir { source, .. } => Some(source),
            Self::LibraryNotFound | Self::InvalidCharOop(_) => None,
        }
    }
}

#[derive(Clone)]
pub struct GciLibrary {
    library: Arc<Library>,
    path: PathBuf,
}

impl GciLibrary {
    pub fn load(lib_path: Option<PathBuf>) -> Result<Self> {
        let path = resolve_library_path(lib_path)?;
        // SAFETY: Loading a dynamic library can execute platform loader hooks.
        // Callers opt into this by selecting the GemStone GCI library path.
        unsafe { Self::load_path(path) }
    }

    pub unsafe fn load_path(path: PathBuf) -> Result<Self> {
        let library = Library::new(&path).map_err(|source| GciError::LibraryLoad {
            path: path.clone(),
            source,
        })?;
        Ok(Self {
            library: Arc::new(library),
            path,
        })
    }

    pub fn path(&self) -> &Path {
        &self.path
    }

    pub unsafe fn gci_init(&self) -> Result<c_int> {
        let init: Symbol<unsafe extern "C" fn() -> c_int> = self.symbol(b"GciInit")?;
        Ok(init())
    }

    pub unsafe fn gci_set_net(
        &self,
        stone_nrs: &CStr,
        host_username: &CStr,
        encrypted_host_password: *const c_char,
        gem_service: &CStr,
    ) -> Result<()> {
        let set_net: Symbol<
            unsafe extern "C" fn(*const c_char, *const c_char, *const c_char, *const c_char),
        > = self.symbol(b"GciSetNet")?;
        set_net(
            stone_nrs.as_ptr(),
            host_username.as_ptr(),
            encrypted_host_password,
            gem_service.as_ptr(),
        );
        Ok(())
    }

    pub unsafe fn gci_encrypt(
        &self,
        password: &CStr,
        buffer: *mut c_char,
        buffer_size: c_uint,
    ) -> Result<*mut c_char> {
        let encrypt: Symbol<
            unsafe extern "C" fn(*const c_char, *mut c_char, c_uint) -> *mut c_char,
        > = self.symbol(b"GciEncrypt")?;
        Ok(encrypt(password.as_ptr(), buffer, buffer_size))
    }

    pub unsafe fn gci_login_ex(
        &self,
        username: &CStr,
        password: &CStr,
        flags: c_uint,
        halt_on_error: c_int,
    ) -> Result<c_int> {
        let login: Symbol<
            unsafe extern "C" fn(*const c_char, *const c_char, c_uint, c_int) -> c_int,
        > = self.symbol(b"GciLoginEx")?;
        Ok(login(
            username.as_ptr(),
            password.as_ptr(),
            flags,
            halt_on_error,
        ))
    }

    pub unsafe fn gci_logout(&self) -> Result<c_int> {
        let logout: Symbol<unsafe extern "C" fn() -> c_int> = self.symbol(b"GciLogout")?;
        Ok(logout())
    }

    pub unsafe fn gci_commit(&self, err: &mut GciErrSType) -> Result<c_int> {
        self.gci_commit_ptr(err as *mut GciErrSType as *mut c_void)
    }

    pub unsafe fn gci_commit_ptr(&self, err: *mut c_void) -> Result<c_int> {
        let commit: Symbol<unsafe extern "C" fn(*mut c_void) -> c_int> =
            self.symbol(b"GciCommit")?;
        Ok(commit(err))
    }

    pub unsafe fn gci_abort(&self, err: &mut GciErrSType) -> Result<c_int> {
        self.gci_abort_ptr(err as *mut GciErrSType as *mut c_void)
    }

    pub unsafe fn gci_abort_ptr(&self, err: *mut c_void) -> Result<c_int> {
        let abort: Symbol<unsafe extern "C" fn(*mut c_void) -> c_int> = self.symbol(b"GciAbort")?;
        Ok(abort(err))
    }

    pub unsafe fn gci_err(&self, err: &mut GciErrSType) -> Result<c_int> {
        self.gci_err_ptr(err as *mut GciErrSType as *mut c_void)
    }

    pub unsafe fn gci_err_ptr(&self, err: *mut c_void) -> Result<c_int> {
        let gci_err: Symbol<unsafe extern "C" fn(*mut c_void) -> c_int> = self.symbol(b"GciErr")?;
        Ok(gci_err(err))
    }

    pub unsafe fn gci_execute_str(&self, source: &CStr, receiver: RawOop) -> Result<RawOop> {
        let execute: Symbol<unsafe extern "C" fn(*const c_char, RawOop) -> RawOop> =
            self.symbol(b"GciExecuteStr")?;
        Ok(execute(source.as_ptr(), receiver))
    }

    pub unsafe fn gci_new_string(&self, value: &CStr) -> Result<RawOop> {
        let new_string: Symbol<unsafe extern "C" fn(*const c_char) -> RawOop> =
            self.symbol(b"GciNewString")?;
        Ok(new_string(value.as_ptr()))
    }

    pub unsafe fn gci_new_symbol(&self, value: &CStr) -> Result<RawOop> {
        let new_symbol: Symbol<unsafe extern "C" fn(*const c_char) -> RawOop> =
            self.symbol(b"GciNewSymbol")?;
        Ok(new_symbol(value.as_ptr()))
    }

    pub unsafe fn gci_flt_to_oop(&self, value: c_double) -> Result<RawOop> {
        let flt_to_oop: Symbol<unsafe extern "C" fn(c_double) -> RawOop> =
            self.symbol(b"GciFltToOop")?;
        Ok(flt_to_oop(value))
    }

    pub unsafe fn gci_oop_to_flt(&self, oop: RawOop, value: *mut c_double) -> Result<c_int> {
        let oop_to_flt: Symbol<unsafe extern "C" fn(RawOop, *mut c_double) -> c_int> =
            self.symbol(b"GciOopToFlt_")?;
        Ok(oop_to_flt(oop, value))
    }

    pub unsafe fn gci_fetch_size(&self, oop: RawOop) -> Result<i64> {
        let fetch_size: Symbol<unsafe extern "C" fn(RawOop) -> i64> =
            self.symbol(b"GciFetchSize_")?;
        Ok(fetch_size(oop))
    }

    pub unsafe fn gci_fetch_bytes(
        &self,
        oop: RawOop,
        start: i64,
        buffer: *mut c_char,
        count: i64,
    ) -> Result<i64> {
        let fetch_bytes: Symbol<unsafe extern "C" fn(RawOop, i64, *mut c_char, i64) -> i64> =
            self.symbol(b"GciFetchBytes_")?;
        Ok(fetch_bytes(oop, start, buffer, count))
    }

    pub unsafe fn gci_fetch_class(&self, oop: RawOop) -> Result<RawOop> {
        let fetch_class: Symbol<unsafe extern "C" fn(RawOop) -> RawOop> =
            self.symbol(b"GciFetchClass")?;
        Ok(fetch_class(oop))
    }

    pub unsafe fn gci_perform(
        &self,
        receiver: RawOop,
        selector: &CStr,
        args: *const RawOop,
        argc: c_int,
    ) -> Result<RawOop> {
        let perform: Symbol<
            unsafe extern "C" fn(RawOop, *const c_char, *const RawOop, c_int) -> RawOop,
        > = self.symbol(b"GciPerform")?;
        Ok(perform(receiver, selector.as_ptr(), args, argc))
    }

    pub unsafe fn gci_new_oop(&self, class_oop: RawOop) -> Result<RawOop> {
        let new_oop: Symbol<unsafe extern "C" fn(RawOop) -> RawOop> = self.symbol(b"GciNewOop")?;
        Ok(new_oop(class_oop))
    }

    pub unsafe fn gci_resolve_symbol(&self, name: &CStr, symbol_list: RawOop) -> Result<RawOop> {
        let resolve: Symbol<unsafe extern "C" fn(*const c_char, RawOop) -> RawOop> =
            self.symbol(b"GciResolveSymbol")?;
        Ok(resolve(name.as_ptr(), symbol_list))
    }

    pub unsafe fn gci_sym_dict_at_put(
        &self,
        dict: RawOop,
        key: &CStr,
        value: RawOop,
    ) -> Result<()> {
        let at_put: Symbol<unsafe extern "C" fn(RawOop, *const c_char, RawOop)> =
            self.symbol(b"GciSymDictAtPut")?;
        at_put(dict, key.as_ptr(), value);
        Ok(())
    }

    pub unsafe fn gci_sym_dict_at_obj_put(
        &self,
        dict: RawOop,
        key: RawOop,
        value: RawOop,
    ) -> Result<()> {
        let at_put: Symbol<unsafe extern "C" fn(RawOop, RawOop, RawOop)> =
            self.symbol(b"GciSymDictAtObjPut")?;
        at_put(dict, key, value);
        Ok(())
    }

    pub unsafe fn gci_str_key_value_dict_at_put(
        &self,
        dict: RawOop,
        key: &CStr,
        value: RawOop,
    ) -> Result<()> {
        let at_put: Symbol<unsafe extern "C" fn(RawOop, *const c_char, RawOop)> =
            self.symbol(b"GciStrKeyValueDictAtPut")?;
        at_put(dict, key.as_ptr(), value);
        Ok(())
    }

    pub unsafe fn gci_str_key_value_dict_at(
        &self,
        dict: RawOop,
        key: &CStr,
        value: *mut RawOop,
    ) -> Result<()> {
        let at: Symbol<unsafe extern "C" fn(RawOop, *const c_char, *mut RawOop)> =
            self.symbol(b"GciStrKeyValueDictAt")?;
        at(dict, key.as_ptr(), value);
        Ok(())
    }

    pub unsafe fn gci_sym_dict_at(
        &self,
        dict: RawOop,
        key: &CStr,
        value: *mut RawOop,
        assoc: *mut RawOop,
    ) -> Result<()> {
        let at: Symbol<unsafe extern "C" fn(RawOop, *const c_char, *mut RawOop, *mut RawOop)> =
            self.symbol(b"GciSymDictAt")?;
        at(dict, key.as_ptr(), value, assoc);
        Ok(())
    }

    pub unsafe fn gci_get_session_id(&self) -> Result<c_int> {
        let get_session_id: Symbol<unsafe extern "C" fn() -> c_int> =
            self.symbol(b"GciGetSessionId")?;
        Ok(get_session_id())
    }

    pub unsafe fn gci_set_session_id(&self, session_id: c_int) -> Result<()> {
        let set_session_id: Symbol<unsafe extern "C" fn(c_int)> =
            self.symbol(b"GciSetSessionId")?;
        set_session_id(session_id);
        Ok(())
    }

    pub unsafe fn gci_needs_commit(&self) -> Result<c_int> {
        let needs_commit: Symbol<unsafe extern "C" fn() -> c_int> =
            self.symbol(b"GciNeedsCommit")?;
        Ok(needs_commit())
    }

    pub unsafe fn gci_in_transaction(&self) -> Result<c_int> {
        let in_transaction: Symbol<unsafe extern "C" fn() -> c_int> =
            self.symbol(b"GciInTransaction")?;
        Ok(in_transaction())
    }

    pub unsafe fn call_optional_oop_export(&self, name: &[u8], oop: RawOop) -> Result<bool> {
        let symbol = self.library.get::<unsafe extern "C" fn(RawOop)>(name);
        if let Ok(function) = symbol {
            function(oop);
            return Ok(true);
        }
        Ok(false)
    }

    fn symbol<T>(&self, name: &[u8]) -> Result<Symbol<'_, T>> {
        unsafe { self.library.get(name) }.map_err(|source| GciError::Symbol {
            path: self.path.clone(),
            symbol: String::from_utf8_lossy(name).to_string(),
            source,
        })
    }
}

pub fn is_smallint(oop: RawOop) -> bool {
    (oop & 0x7) == TAG_SMALLINT
}

pub fn is_smalldouble(oop: RawOop) -> bool {
    (oop & 0x7) == TAG_SMALLDOUBLE
}

pub fn smallint_to_i64(oop: RawOop) -> i64 {
    (oop as i64) >> SMALLINT_SHIFT
}

pub fn i64_to_smallint(value: i64) -> RawOop {
    ((value << SMALLINT_SHIFT) as RawOop) | TAG_SMALLINT
}

pub fn is_char(oop: RawOop) -> bool {
    (oop & 0xFF) == CHAR_TAG_BYTE && (oop & 0x6) == TAG_SPECIAL
}

pub fn char_from_oop(oop: RawOop) -> Result<char> {
    let codepoint = ((oop >> 8) & 0x1F_FFFF) as u32;
    char::from_u32(codepoint).ok_or(GciError::InvalidCharOop(oop))
}

pub fn char_to_oop(value: char) -> RawOop {
    ((value as u32 as RawOop) << 8) | CHAR_TAG_BYTE
}

pub fn resolve_library_path(lib_path: Option<PathBuf>) -> Result<PathBuf> {
    if let Some(path) = lib_path {
        return Ok(path);
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
    Err(GciError::LibraryNotFound)
}

pub fn find_gcirpc_in_dir(dir: &Path) -> Result<Option<PathBuf>> {
    if !dir.is_dir() {
        return Ok(None);
    }
    let mut candidates = Vec::new();
    for entry in fs::read_dir(dir).map_err(|source| GciError::ReadDir {
        path: dir.to_path_buf(),
        source,
    })? {
        let entry = entry.map_err(|source| GciError::ReadDir {
            path: dir.to_path_buf(),
            source,
        })?;
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

fn c_char_array_to_string(value: &[c_char]) -> String {
    let bytes: Vec<u8> = value
        .iter()
        .take_while(|byte| **byte != 0)
        .map(|byte| *byte as u8)
        .collect();
    String::from_utf8_lossy(&bytes).into_owned()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn smallint_helpers_round_trip_signed_values() {
        for value in [-42, -1, 0, 1, 42] {
            assert_eq!(smallint_to_i64(i64_to_smallint(value)), value);
        }
    }

    #[test]
    fn oop_helpers_identify_special_values() {
        assert!(Oop::NIL.is_nil());
        assert!(Oop::TRUE.is_boolean());
        assert!(Oop::FALSE.is_boolean());
        assert_eq!(Oop::TRUE.as_bool(), Some(true));
        assert_eq!(Oop::FALSE.as_bool(), Some(false));
        assert!(Oop(i64_to_smallint(7)).is_smallint());
        assert_eq!(Oop(i64_to_smallint(7)).as_smallint(), Some(7));
    }

    #[test]
    fn char_helpers_round_trip_unicode_values() {
        for value in ['A', '\0', 'λ'] {
            let oop = Oop::from_char(value);
            assert!(oop.is_char());
            assert_eq!(oop.as_char().unwrap(), Some(value));
            assert_eq!(char_from_oop(char_to_oop(value)).unwrap(), value);
        }
    }
}
