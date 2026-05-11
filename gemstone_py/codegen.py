"""Generate typed Python wrappers for registered GemStone Protocol classes."""

from __future__ import annotations

import argparse
import inspect
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from importlib import import_module
from pathlib import Path
from types import ModuleType
from typing import Any, Final, Literal, TypeVar

from gemstone_py.oop import gemstone_class_name

F = TypeVar("F", bound=Callable[..., Any])
ReturnKind = Literal["value", "none", "self_oop"]

SELECTOR_ATTR: Final = "__gemstone_selector__"
ASYNC_ATTR: Final = "__gemstone_codegen_async__"


@dataclass(frozen=True)
class GeneratedFile:
    """One file produced by ``gemstone-codegen``."""

    protocol_name: str
    class_name: str
    path: Path
    source: str
    up_to_date: bool
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class GeneratedWrapper:
    """Generated source plus metadata for one registered protocol class."""

    protocol_name: str
    class_name: str
    gemstone_class_name: str
    source: str
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class _PropertySpec:
    python_name: str
    selector: str
    annotation: str


@dataclass(frozen=True)
class _ArgSpec:
    python_name: str
    annotation: str


@dataclass(frozen=True)
class _MethodSpec:
    python_name: str
    selector: str
    args: tuple[_ArgSpec, ...]
    class_side: bool
    return_kind: ReturnKind
    return_annotation: str

    @property
    def arg_names(self) -> tuple[str, ...]:
        """Return the Python argument names for this method."""
        return tuple(arg.python_name for arg in self.args)


def gemstone_selector(selector: str) -> Callable[[F], F]:
    """Pin the exact Smalltalk selector for a generated wrapper method."""
    if not selector:
        raise ValueError("selector must not be empty")

    def decorator(fn: F) -> F:
        setattr(fn, SELECTOR_ATTR, selector)
        return fn

    return decorator


def selector_for_method(
    python_name: str,
    arg_names: Sequence[str],
    *,
    explicit: str | None = None,
) -> str:
    """
    Return the Smalltalk selector for a Python method name and argument list.

    The default convention maps ``snake_case`` to ``camelCase``. Positional
    arguments turn that base name into a Smalltalk keyword selector:
    ``find_by_id(id)`` becomes ``findById:`` and
    ``transfer_to(user_id, by_user_id)`` becomes ``transferTo:byUserId:``.
    Use ``@gemstone_selector(...)`` when the Smalltalk selector cannot be
    inferred cleanly from the Python spelling.
    """
    if explicit is not None:
        _validate_selector_arity(explicit, len(arg_names), python_name)
        return explicit
    if not arg_names:
        return _snake_to_camel(python_name)
    first_keyword = _snake_to_camel(python_name)
    later_keywords = tuple(_snake_to_camel(arg_name) for arg_name in arg_names[1:])
    return "".join(f"{keyword}:" for keyword in (first_keyword, *later_keywords))


def generate_wrapper(protocol_cls: type[Any]) -> str:
    """Generate the Python source for one registered GemStone Protocol class."""
    return generate_wrapper_details(protocol_cls).source


def generate_wrapper_details(protocol_cls: type[Any]) -> GeneratedWrapper:
    """Generate Python source plus warnings for one registered protocol class."""
    gs_name = gemstone_class_name(protocol_cls)
    if gs_name is None:
        raise ValueError(f"{protocol_cls.__qualname__} is not decorated with @gemstone_class")

    wrapper_name = _wrapper_class_name(protocol_cls.__name__)
    properties, methods, warnings = _collect_specs(protocol_cls, wrapper_name)
    source = _render_source(
        wrapper_name=wrapper_name,
        protocol_name=protocol_cls.__name__,
        module_name=protocol_cls.__module__,
        gs_name=gs_name,
        properties=properties,
        methods=methods,
        include_async=bool(getattr(protocol_cls, ASYNC_ATTR, False)),
        warnings=warnings,
    )
    return GeneratedWrapper(
        protocol_name=protocol_cls.__name__,
        class_name=wrapper_name,
        gemstone_class_name=gs_name,
        source=source,
        warnings=warnings,
    )


def generate_package(
    module_name: str,
    output_dir: Path | str,
    *,
    check: bool = False,
) -> tuple[GeneratedFile, ...]:
    """
    Generate wrapper files for all registered Protocol classes in ``module``.

    Generated files are intended to be checked into the application repository
    so editors and type checkers can see the concrete wrappers.
    """
    module = import_module(module_name)
    output_path = Path(output_dir)
    if not check:
        output_path.mkdir(parents=True, exist_ok=True)

    generated = tuple(generate_wrapper_details(cls) for cls in _iter_registered_classes(module))
    files: list[GeneratedFile] = []
    init_path = output_path / "__init__.py"
    init_source = _render_package_init(generated)
    files.append(
        _write_or_check(
            protocol_name="__init__",
            class_name="__init__",
            path=init_path,
            source=init_source,
            warnings=(),
            check=check,
        )
    )
    for wrapper in generated:
        path = output_path / f"{_to_snake(wrapper.class_name)}.py"
        files.append(
            _write_or_check(
                protocol_name=wrapper.protocol_name,
                class_name=wrapper.class_name,
                path=path,
                source=wrapper.source,
                warnings=wrapper.warnings,
                check=check,
            )
        )
    return tuple(files)


def build_parser() -> argparse.ArgumentParser:
    """Build the ``gemstone-codegen`` command-line parser."""
    parser = argparse.ArgumentParser(
        prog="gemstone-codegen",
        description="Generate typed GemStone wrappers from @gemstone_class Protocols.",
    )
    parser.add_argument(
        "--module",
        required=True,
        help="Python module containing @gemstone_class Protocol classes.",
    )
    parser.add_argument(
        "--output",
        required=True,
        type=Path,
        help="Directory where generated wrapper modules should be written.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail if generated files are missing or out of date without writing them.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the ``gemstone-codegen`` CLI."""
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        files = generate_package(args.module, args.output, check=bool(args.check))
    except (ImportError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2

    stale = [file for file in files if not file.up_to_date]
    for file in files:
        status = "ok" if file.up_to_date else ("stale" if args.check else "wrote")
        print(f"{status}: {file.path}")
        for warning in file.warnings:
            print(f"warning: {file.protocol_name}: {warning}", file=sys.stderr)
    if args.check and stale:
        print(f"{len(stale)} generated file(s) are out of date", file=sys.stderr)
        return 1
    return 0


def main_entry() -> None:
    """Console-script wrapper for ``gemstone-codegen``."""
    raise SystemExit(main())


def _iter_registered_classes(module: ModuleType) -> tuple[type[Any], ...]:
    classes: list[type[Any]] = []
    for _name, obj in inspect.getmembers(module, inspect.isclass):
        if obj.__module__ != module.__name__:
            continue
        if gemstone_class_name(obj) is None:
            continue
        classes.append(obj)
    return tuple(sorted(classes, key=lambda cls: cls.__name__))


def _collect_specs(
    protocol_cls: type[Any],
    wrapper_name: str,
) -> tuple[tuple[_PropertySpec, ...], tuple[_MethodSpec, ...], tuple[str, ...]]:
    properties: list[_PropertySpec] = []
    methods: list[_MethodSpec] = []
    warnings: list[str] = []
    seen_properties: set[str] = set()

    annotations = getattr(protocol_cls, "__annotations__", {})
    if isinstance(annotations, dict):
        for python_name, annotation in annotations.items():
            if python_name.startswith("_"):
                continue
            properties.append(
                _PropertySpec(
                    python_name,
                    _snake_to_camel(python_name),
                    _annotation_to_source(annotation, protocol_cls.__name__, wrapper_name),
                )
            )
            seen_properties.add(python_name)

    for python_name, member in protocol_cls.__dict__.items():
        if python_name.startswith("_"):
            continue
        if isinstance(member, property):
            if python_name not in seen_properties:
                return_annotation = (
                    inspect.signature(member.fget).return_annotation
                    if member.fget is not None
                    else inspect.Signature.empty
                )
                properties.append(
                    _PropertySpec(
                        python_name,
                        _selector_for_callable(python_name, ()),
                        _annotation_to_source(
                            return_annotation,
                            protocol_cls.__name__,
                            wrapper_name,
                        ),
                    )
                )
                seen_properties.add(python_name)
            continue
        if isinstance(member, classmethod):
            spec, warning = _method_spec(
                python_name,
                member.__func__,
                class_side=True,
                protocol_name=protocol_cls.__name__,
                wrapper_name=wrapper_name,
            )
            methods.append(spec)
            if warning is not None:
                warnings.append(warning)
            continue
        if inspect.isfunction(member):
            spec, warning = _method_spec(
                python_name,
                member,
                class_side=False,
                protocol_name=protocol_cls.__name__,
                wrapper_name=wrapper_name,
            )
            methods.append(spec)
            if warning is not None:
                warnings.append(warning)

    return tuple(properties), tuple(methods), tuple(warnings)


def _method_spec(
    python_name: str,
    fn: Callable[..., Any],
    *,
    class_side: bool,
    protocol_name: str,
    wrapper_name: str,
) -> tuple[_MethodSpec, str | None]:
    signature = inspect.signature(fn)
    params = list(signature.parameters.values())
    if params and params[0].name in {"self", "cls"}:
        params = params[1:]
    arg_specs: list[_ArgSpec] = []
    for param in params:
        if param.kind not in {
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            inspect.Parameter.KEYWORD_ONLY,
        }:
            raise ValueError(
                f"{python_name} uses unsupported parameter kind {param.kind.description}"
            )
        if param.default is not inspect.Parameter.empty:
            raise ValueError(
                f"{python_name} uses default arguments; generated wrappers require "
                "explicit arguments"
            )
        arg_specs.append(
            _ArgSpec(
                param.name,
                _annotation_to_source(param.annotation, protocol_name, wrapper_name),
            )
        )

    arg_names = tuple(arg.python_name for arg in arg_specs)
    selector = _selector_for_callable(python_name, tuple(arg_names), fn=fn)
    return_kind, return_annotation = _return_spec(
        signature.return_annotation,
        protocol_name,
        wrapper_name,
    )
    warning = None
    if len(arg_names) > 1 and getattr(fn, SELECTOR_ATTR, None) is None:
        warning = (
            f"auto-inferred selector {selector!r} for multi-argument method "
            f"{python_name!r}; use @gemstone_selector(...) if the GemStone selector differs"
        )
    return _MethodSpec(
        python_name=python_name,
        selector=selector,
        args=tuple(arg_specs),
        class_side=class_side,
        return_kind=return_kind,
        return_annotation=return_annotation,
    ), warning


def _selector_for_callable(
    python_name: str,
    arg_names: Sequence[str],
    fn: Callable[..., Any] | None = None,
) -> str:
    explicit = getattr(fn, SELECTOR_ATTR, None) if fn is not None else None
    if explicit is not None and not isinstance(explicit, str):
        raise ValueError(f"{python_name} has a non-string GemStone selector")
    return selector_for_method(python_name, arg_names, explicit=explicit)


def _render_source(
    *,
    wrapper_name: str,
    protocol_name: str,
    module_name: str,
    gs_name: str,
    properties: Sequence[_PropertySpec],
    methods: Sequence[_MethodSpec],
    include_async: bool,
    warnings: Sequence[str],
) -> str:
    lines = [
        '"""Generated GemStone wrappers.',
        "",
        f"Source Protocol: {module_name}.{protocol_name}",
        'Regenerate with `gemstone-codegen`; do not edit by hand.',
        '"""',
        "",
        "from __future__ import annotations",
        "",
        "from typing import Any",
        "",
        "from gemstone_py import TypedOop",
        "",
        "",
    ]
    if warnings:
        lines.append("# Code generation warnings:")
        for warning in warnings:
            lines.append(f"# - {warning}")
        lines.append("")
    lines.extend(_literal_helpers())
    lines.append("")
    lines.append("")
    lines.extend(_render_class(wrapper_name, gs_name, properties, methods, async_class=False))
    if include_async:
        lines.append("")
        lines.append("")
        lines.extend(
            _render_class(
                f"Async{wrapper_name}",
                gs_name,
                properties,
                methods,
                async_class=True,
            )
        )
    public_names = [wrapper_name]
    if include_async:
        public_names.append(f"Async{wrapper_name}")
    lines.append("")
    lines.append("")
    lines.append(f"__all__ = {public_names!r}")
    lines.append("")
    return "\n".join(lines)


def _literal_helpers() -> list[str]:
    return [
        "def _smalltalk_literal(value: Any) -> str:",
        "    if value is None:",
        "        return \"nil\"",
        "    if value is True:",
        "        return \"true\"",
        "    if value is False:",
        "        return \"false\"",
        "    if isinstance(value, str):",
        "        return \"'\" + value.replace(\"'\", \"''\") + \"'\"",
        "    if isinstance(value, int | float):",
        "        return repr(value)",
        "    custom = getattr(value, \"__smalltalk_source__\", None)",
        "    if callable(custom):",
        "        return str(custom())",
        "    raise TypeError(f\"cannot convert {type(value).__name__} to a Smalltalk literal\")",
        "",
        "",
        "def _argument_to_oop(value: Any) -> int:",
        "    if hasattr(value, \"oop\"):",
        "        return int(getattr(value, \"oop\"))",
        "    return int(value)",
        "",
        "",
        "def _build_smalltalk_source(receiver: str, selector: str, args: tuple[Any, ...]) -> str:",
        "    keywords = tuple(part for part in selector.split(\":\")[:-1] if part)",
        "    if not keywords:",
        "        if args:",
        "            raise TypeError(f\"selector {selector!r} does not accept arguments\")",
        "        return f\"{receiver} {selector}\"",
        "    if len(keywords) != len(args):",
        "        raise TypeError(f\"selector {selector!r} expects {len(keywords)} argument(s)\")",
        "    pieces = [receiver]",
        "    for keyword, arg in zip(keywords, args):",
        "        pieces.append(f\"{keyword}:\")",
        "        pieces.append(_smalltalk_literal(arg))",
        "    return \" \".join(pieces)",
    ]


def _render_class(
    class_name: str,
    gs_name: str,
    properties: Sequence[_PropertySpec],
    methods: Sequence[_MethodSpec],
    *,
    async_class: bool,
) -> list[str]:
    base_name = "TypedOop[Any]"
    lines = [
        f"class {class_name}({base_name}):",
        f"    __gemstone_class_name__ = {gs_name!r}",
        "",
    ]
    if not properties and not methods:
        lines.append("    pass")
        return lines
    for prop in properties:
        lines.extend(_render_property(prop, async_class=async_class))
        lines.append("")
    for method in methods:
        lines.extend(_render_method(class_name, method, async_class=async_class))
        lines.append("")
    if lines[-1] == "":
        lines.pop()
    return lines


def _render_property(prop: _PropertySpec, *, async_class: bool) -> list[str]:
    if async_class:
        return [
            f"    async def {prop.python_name}(self) -> {prop.annotation}:",
            "        session = self.session",
            "        if session is None:",
            "            raise RuntimeError(\"TypedOop has no associated GemStoneSession\")",
            f"        return await session.perform_value(int(self), {prop.selector!r})",
        ]
    return [
        "    @property",
        f"    def {prop.python_name}(self) -> {prop.annotation}:",
        f"        return self.send({prop.selector!r})",
    ]


def _render_method(
    class_name: str,
    method: _MethodSpec,
    *,
    async_class: bool,
) -> list[str]:
    args = ", ".join(f"{arg.python_name}: {arg.annotation}" for arg in method.args)
    call_args = ", ".join(method.arg_names)
    call_tuple = _tuple_expression(method.arg_names)
    return_annotation = (
        class_name if method.return_kind == "self_oop" else method.return_annotation
    )
    if method.class_side:
        prefix = "async " if async_class else ""
        await_prefix = "await " if async_class else ""
        signature_args = f"session: Any{', ' if args else ''}{args}"
        signature = (
            f"    {prefix}def {method.python_name}(cls, {signature_args}) "
            f"-> {return_annotation}:"
        )
        lines = [
            "    @classmethod",
            signature,
            "        source = _build_smalltalk_source(",
            "            cls.__gemstone_class_name__,",
            f"            {method.selector!r},",
            f"            {call_tuple},",
            "        )",
        ]
        if method.return_kind == "self_oop":
            lines.extend(
                [
                    f"        oop = {await_prefix}session.execute_oop(source)",
                    "        return cls(",
                    "            oop,",
                    "            session=session,",
                    "            wrapper_type=cls,",
                    "            gemstone_class_name=cls.__gemstone_class_name__,",
                    "        )",
                ]
            )
        elif method.return_kind == "none":
            lines.append(f"        {await_prefix}session.eval(source)")
        else:
            lines.append(f"        return {await_prefix}session.eval(source)")
        return lines
    if async_class:
        signature_args = f"{', ' if args else ''}{args}"
        raw_args = _oop_tuple_expression(method.arg_names)
        call_suffix = ", *raw_args" if call_args else ""
        signature = (
            f"    async def {method.python_name}(self{signature_args}) "
            f"-> {return_annotation}:"
        )
        lines = [
            signature,
            "        session = self.session",
            "        if session is None:",
            "            raise RuntimeError(\"TypedOop has no associated GemStoneSession\")",
        ]
        if call_args:
            lines.append(f"        raw_args = {raw_args}")
        if method.return_kind == "self_oop":
            lines.extend(
                [
                    f"        oop = await session.perform_oop("
                    f"int(self), {method.selector!r}{call_suffix})",
                    "        return type(self)(",
                    "            oop,",
                    "            session=session,",
                    "            wrapper_type=type(self),",
                    "            gemstone_class_name=self.__gemstone_class_name__,",
                    "        )",
                ]
            )
        elif method.return_kind == "none":
            lines.append(
                f"        await session.perform_value("
                f"int(self), {method.selector!r}{call_suffix})"
            )
        else:
            lines.append(
                f"        return await session.perform_value("
                f"int(self), {method.selector!r}{call_suffix})"
            )
        return lines
    signature_args = f"{', ' if args else ''}{args}"
    call_suffix = f", {call_args}" if call_args else ""
    lines = [f"    def {method.python_name}(self{signature_args}) -> {return_annotation}:"]
    if method.return_kind == "self_oop":
        lines.extend(
            [
                f"        oop = self.send_oop({method.selector!r}{call_suffix})",
                "        return type(self)(",
                "            oop,",
                "            session=self.session,",
                "            wrapper_type=type(self),",
                "            gemstone_class_name=self.__gemstone_class_name__,",
                "        )",
            ]
        )
    elif method.return_kind == "none":
        lines.append(f"        self.send({method.selector!r}{call_suffix})")
    else:
        lines.append(f"        return self.send({method.selector!r}{call_suffix})")
    return lines


def _render_package_init(wrappers: Sequence[GeneratedWrapper]) -> str:
    lines = [
        '"""Generated GemStone wrapper package."""',
        "",
        "from __future__ import annotations",
        "",
    ]
    public_names: list[str] = []
    for wrapper in wrappers:
        module_name = _to_snake(wrapper.class_name)
        names = [wrapper.class_name]
        if f"class Async{wrapper.class_name}(" in wrapper.source:
            names.append(f"Async{wrapper.class_name}")
        lines.append(f"from .{module_name} import {', '.join(sorted(names))}")
        public_names.extend(names)
    lines.append("")
    lines.append(f"__all__ = {public_names!r}")
    lines.append("")
    return "\n".join(lines)


def _write_or_check(
    *,
    protocol_name: str,
    class_name: str,
    path: Path,
    source: str,
    warnings: tuple[str, ...],
    check: bool,
) -> GeneratedFile:
    current = path.read_text(encoding="utf-8") if path.exists() else None
    up_to_date = current == source
    if not check and not up_to_date:
        path.write_text(source, encoding="utf-8")
        up_to_date = True
    return GeneratedFile(
        protocol_name=protocol_name,
        class_name=class_name,
        path=path,
        source=source,
        up_to_date=up_to_date,
        warnings=warnings,
    )


def _validate_selector_arity(selector: str, argc: int, python_name: str) -> None:
    colon_count = selector.count(":")
    if colon_count != argc:
        raise ValueError(
            f"{python_name} selector {selector!r} has {colon_count} keyword(s), "
            f"but the Python method has {argc} argument(s)"
        )


def _return_spec(
    annotation: Any,
    protocol_name: str,
    wrapper_name: str,
) -> tuple[ReturnKind, str]:
    normalized = _normalized_annotation(annotation)
    if normalized is None:
        return "value", "Any"
    if normalized in {"None", "NoneType"}:
        return "none", "None"
    if normalized in {protocol_name, wrapper_name, "Self", "typing.Self"}:
        return "self_oop", wrapper_name
    return "value", _safe_annotation_source(normalized)


def _annotation_to_source(annotation: Any, protocol_name: str, wrapper_name: str) -> str:
    normalized = _normalized_annotation(annotation)
    if normalized is None:
        return "Any"
    if normalized in {protocol_name, wrapper_name, "Self", "typing.Self"}:
        return wrapper_name
    return _safe_annotation_source(normalized)


def _normalized_annotation(annotation: Any) -> str | None:
    if annotation is inspect.Signature.empty:
        return None
    if annotation is None:
        return "None"
    if annotation is Any:
        return "Any"
    if isinstance(annotation, str):
        return _strip_annotation_quotes(annotation)
    module = getattr(annotation, "__module__", "")
    qualname = getattr(annotation, "__qualname__", None)
    name = getattr(annotation, "__name__", None)
    if module == "builtins" and isinstance(qualname, str):
        return "None" if qualname == "NoneType" else qualname
    if isinstance(name, str):
        return name
    return None


def _safe_annotation_source(annotation: str) -> str:
    if annotation in {"Any", "None", "str", "int", "float", "bool", "bytes", "object"}:
        return annotation
    return "Any"


def _strip_annotation_quotes(annotation: str) -> str:
    text = annotation.strip()
    while len(text) >= 2 and text[0] == text[-1] and text[0] in {"'", '"'}:
        text = text[1:-1].strip()
    return text


def _wrapper_class_name(protocol_name: str) -> str:
    for suffix in ("Protocol", "Proto"):
        if protocol_name.endswith(suffix) and len(protocol_name) > len(suffix):
            return protocol_name[: -len(suffix)]
    return protocol_name


def _snake_to_camel(name: str) -> str:
    parts = [part for part in name.split("_") if part]
    if not parts:
        return name
    return parts[0] + "".join(part[:1].upper() + part[1:] for part in parts[1:])


def _to_snake(name: str) -> str:
    chars: list[str] = []
    previous_lower = False
    for char in name:
        if char.isupper() and previous_lower:
            chars.append("_")
        chars.append(char.lower())
        previous_lower = char.islower() or char.isdigit()
    return "".join(chars)


def _tuple_expression(arg_names: Sequence[str]) -> str:
    if not arg_names:
        return "()"
    if len(arg_names) == 1:
        return f"({arg_names[0]},)"
    return "(" + ", ".join(arg_names) + ")"


def _oop_tuple_expression(arg_names: Sequence[str]) -> str:
    if not arg_names:
        return "()"
    calls = [f"_argument_to_oop({arg_name})" for arg_name in arg_names]
    if len(calls) == 1:
        return f"({calls[0]},)"
    return "(" + ", ".join(calls) + ")"


__all__ = [
    "GeneratedFile",
    "GeneratedWrapper",
    "gemstone_selector",
    "generate_package",
    "generate_wrapper",
    "generate_wrapper_details",
    "selector_for_method",
]


if __name__ == "__main__":
    main_entry()
