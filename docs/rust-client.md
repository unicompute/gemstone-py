# Rust Client

Rust applications should use the separate `gemstone-rs` workspace to talk to
GemStone/S without Python in the process. When checked out beside this
repository, it lives at `../gemstone-rs`.

The split is:

| Crate | Purpose |
| --- | --- |
| `gemstone-rs/crates/gemstone-gci` | Low-level dynamic `libgcirpc` loader, OOP constants, and raw GCI ABI calls. |
| `gemstone-rs/crates/gemstone-rs` | Safe Rust API with `Config`, `Session`, `Oop`, `Value`, and transaction helpers. |
| `gemstone-py/gemstone-py-native` | Thin PyO3 wrapper around a vendored `gemstone-gci` copy for the Python fast path. |

The public Cargo package is `gemstone-rs`. In Rust source code, import it as
`gemstone_rs`.

The Rust client intentionally does not mirror every Python convenience. Recent
Python helpers such as generated wrappers, explicit value converters, bulk root
helpers, and conflict-formatting reports remain Python-side ergonomics. The
Rust workspace keeps its surface smaller: raw GCI access, conservative value
conversion, OOP handles, and explicit transaction control.

## Environment

Set the same GemStone environment used by `gemstone-py`:

```bash
export GS_LIB=/opt/gemstone/product/lib
export GS_STONE=gs64stone
export GS_STONE_NAME=gs64stone
export GS_USERNAME=DataCurator
export GS_PASSWORD=swordfish
```

`GS_LIB_PATH` can point directly at a specific `libgcirpc` file. Otherwise
`gemstone-gci` searches `GS_LIB` and `GEMSTONE/lib`.

## Evaluate Smalltalk

```rust
use gemstone_rs::{Config, Session, Value};

fn main() -> gemstone_rs::Result<()> {
    let config = Config::from_env()?;
    let mut session = Session::login(config)?;

    let value = session.eval("3 + 4")?;
    assert_eq!(value, Value::SmallInt(7));

    session.logout()?;
    Ok(())
}
```

Run the repository example:

```bash
cd ../gemstone-rs
cargo run -p gemstone-rs --example eval
```

## Perform Selectors

Use `Oop` explicitly when you want raw GemStone object references:

```rust
use gemstone_rs::{Config, Session};

fn main() -> gemstone_rs::Result<()> {
    let config = Config::from_env()?;
    let mut session = Session::login(config)?;

    let system = session.resolve("System")?;
    let result = session.perform(system, "myUserProfile", &[])?;
    println!("{result:?}");

    let seven = session.smallint_oop(7);
    let printed = session.perform(seven, "printString", &[])?;
    println!("{printed:?}");

    session.logout()?;
    Ok(())
}
```

`Session` is deliberately not `Send` or `Sync`; keep one session on one thread
until GemStone GCI threading behavior is proven safe for broader sharing.

## Values, Globals, and Handles

`Value` covers the conservative automatic conversions: `nil`, booleans, small
integers, characters, strings, and raw `Oop` values. Use `execute()` when you
want the raw OOP from an expression instead of automatic conversion.

```rust
use gemstone_rs::{Config, Session, Value};

let mut session = Session::login(Config::from_env()?)?;

let seven = session.smallint_oop(7);
let flag = session.bool_oop(true);
let text = session.new_string("hello from Rust")?;

session.global_put("GemStoneRsText", text)?;
let stored = session.global_get("GemStoneRsText")?;
let stored_text = session.fetch_string(stored)?;
assert_eq!(stored_text, "hello from Rust");

let oop = session.value_to_oop(&Value::Char('A'))?;
assert!(oop.is_char());

let handle = session.retain_oop(stored)?;
let retained_oop = handle.oop();
println!("retained {retained_oop:?}, seven={seven:?}, flag={flag:?}");
handle.release()?;
```

`retain_oop()` adds an object to GemStone's export set when the loaded GCI
library exposes an export-set function. The returned `OopHandle` removes it on
`Drop`, so handles are intended for short-lived Rust scopes rather than global
storage.

## Transaction Helpers

```rust
let mut session = Session::login(Config::from_env()?)?;

if session.needs_commit()? {
    session.commit()?;
}

session.abort()?;
session.logout()?;
```

`Session` also logs out on `Drop`, so explicit `logout()` is recommended but not
required for ordinary scope exits.

## Live Rust Smoke Test

The Rust crates include non-live unit tests by default. To verify a real stone,
set the normal GemStone environment plus `GS_RUN_LIVE_RUST=1`:

```bash
cd ../gemstone-rs
GS_RUN_LIVE_RUST=1 cargo test -p gemstone-rs live_eval_smoke_returns_seven_when_enabled
```
