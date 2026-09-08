"""Casdoor MCP server — auto-discovery, grouping, and dispatch."""

import inspect
import re
import string
import typing
from functools import wraps
from urllib.parse import urlsplit, urlunsplit

import httpx
import pydantic_core
from mcp.server.mcpserver import Image, MCPServer
from mcp.types import ContentBlock, TextContent

from . import tools as _tools_module
from .client import APIError
from .registry import ROOT

mcp = MCPServer("casdoor")

_URL_RE = re.compile(r"[a-z][a-z0-9+.-]*://[^\s'\"<>]+", re.IGNORECASE)
_RELATIVE_QUERY_RE = re.compile(r"/[^\s?,'\"<>]*\?[^ \t\r\n,'\"<>]*")
_SECRET_VALUE_RE = re.compile(
    r"""(?ix)
    (["']?(?:authorization|token|api[_-]?key|secret|password|credential|dsn)
    ["']?\s*[:=]\s*)
    (?:["'][^"']*["']|\[[^\]]*\]|\{[^}]*\}|[^,\s}]+)
    """
)
_AUTHORIZATION_RE = re.compile(
    r"(?i)(authorization\s*[:=]\s*)(?:bearer|basic)\s+[^\s,;]+"
)


def _redact_error_text(value: object) -> str:
    """Remove credentials and query values from an error string."""
    text = str(value)

    def _redact_url(match: re.Match[str]) -> str:
        try:
            parts = urlsplit(match.group())
            host = parts.hostname
            if host is None:
                return "<redacted-url>"
            if ":" in host:
                host = f"[{host}]"
            try:
                port = parts.port
            except ValueError:
                port = None
            netloc = f"{host}:{port}" if port is not None else host
            return urlunsplit((parts.scheme, netloc, parts.path, "", ""))
        except ValueError:
            return "<redacted-url>"

    text = _URL_RE.sub(_redact_url, text)
    text = _RELATIVE_QUERY_RE.sub(lambda match: match.group().split("?", 1)[0], text)
    text = _AUTHORIZATION_RE.sub(r"\1<redacted>", text)
    return _SECRET_VALUE_RE.sub(r"\1<redacted>", text)


def _error_result(exc: ValueError | APIError | httpx.RequestError) -> dict[str, str]:
    if isinstance(exc, httpx.RequestError):
        try:
            request = exc.request
        except RuntimeError:
            request = None
        method = request.method if request is not None else "REQUEST"
        path = request.url.path if request is not None else "<unknown path>"
        cause = _redact_error_text(exc) or "request failed"
        return {
            "error": (
                f"Casdoor transport failure: {method} {path}: "
                f"{type(exc).__name__}: {cause}"
            )
        }
    return {"error": _redact_error_text(exc)}


def _safe_tool(fn):
    """Convert expected failures for every registered public operation."""
    @wraps(fn)
    def wrapped(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except (ValueError, APIError) as exc:
            return _error_result(exc)
        except httpx.RequestError as exc:
            return _error_result(exc)

    return wrapped


def _compact(fn):
    """Serialize a data result as one-line JSON.

    The SDK pretty-prints non-string results (`indent=2`), which costs the
    caller ~20% more tokens for nothing; a ready TextContent passes through
    untouched. Strings, content blocks and images keep the SDK path. Mirrors
    fn's sync/async flavor so a sync tool stays on the SDK worker thread.
    """
    def to_content(result):
        if result is None or isinstance(result, str | ContentBlock | Image):
            return result
        return TextContent(
            type="text", text=pydantic_core.to_json(result, fallback=str).decode()
        )

    if inspect.iscoroutinefunction(fn):
        @wraps(fn)
        async def async_compact(*args, **kwargs):
            return to_content(await fn(*args, **kwargs))
        return async_compact

    @wraps(fn)
    def sync_compact(*args, **kwargs):
        return to_content(fn(*args, **kwargs))
    return sync_compact


# -- Helpers ------------------------------------------------------------------


def _to_pascal(name: str) -> str:
    """get_server -> GetServer"""
    return "".join(w.capitalize() for w in name.split("_"))


def _parse_bool(val, default: bool) -> bool:
    if val is None:
        return default
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        return val.lower() in ("1", "true", "yes")
    return bool(val)


def _is_bool_hint(hint) -> bool:
    """Check if a type hint is bool or Optional[bool]."""
    if hint is bool:
        return True
    args = typing.get_args(hint)
    return bool in args if args else False


def _coerce_call(fn, params: dict):
    """Coerce JSON-parsed params to match function signature, then call fn."""
    sig = inspect.signature(fn)
    hints = typing.get_type_hints(fn)
    named_params = {
        name: param
        for name, param in sig.parameters.items()
        if param.kind
        not in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD)
    }
    accepts_extra_params = any(
        param.kind is inspect.Parameter.VAR_KEYWORD for param in sig.parameters.values()
    )
    missing = [
        name
        for name, param in named_params.items()
        if param.default is inspect.Parameter.empty and name not in params
    ]
    if missing:
        raise ValueError(f"Missing required parameters: {missing}")

    extra_params = {name: value for name, value in params.items() if name not in named_params}
    if extra_params and not accepts_extra_params:
        raise ValueError(f"Invalid parameters: {sorted(extra_params)}")

    kwargs = {}
    for name, param in named_params.items():
        if name not in params:
            continue
        val = params[name]
        hint = hints.get(name)
        if hint and _is_bool_hint(hint) and not isinstance(val, bool):
            default = param.default
            if default is inspect.Parameter.empty or default is None:
                default = False
            val = _parse_bool(val, default)
        kwargs[name] = val
    kwargs.update(extra_params)
    return fn(**kwargs)


# -- Module-level state (populated by _register_tools) -----------------------

_group_ops: dict[str, dict] = {}    # {group_name: {PascalName: fn}}
_all_grouped: dict[str, str] = {}   # {PascalName: group_name}


def _build_help(group_name: str) -> str:
    """Build help text from operation functions in a group.

    A VAR_KEYWORD parameter is rendered as `**kwargs`, never as a plain name:
    extras reach Casdoor as top-level body fields, so a caller that reads
    `kwargs` as a parameter name sends a body carrying one literal `kwargs`
    field -- which Casdoor ignores -- while every field it meant to set is
    missing. This help text is the only signature a caller sees at call time,
    so it has to spell the wire contract the way SPEC.md does.
    """
    ops = _group_ops[group_name]
    lines = []
    for pascal_name, fn in ops.items():
        params = ", ".join(
            f"**{name}" if param.kind is inspect.Parameter.VAR_KEYWORD else name
            for name, param in inspect.signature(fn).parameters.items()
        )
        doc = fn.__doc__.split("\n")[0]
        lines.append(f"  {pascal_name}({params}) -- {doc}")
    return f"{len(lines)} operations available:\n" + "\n".join(lines)


def _dispatch(operation: str, group_name: str, params: dict):
    """Dispatch an operation call to the right function."""
    ops = _group_ops[group_name]
    if operation not in ops:
        if operation in _all_grouped:
            correct = _all_grouped[operation]
            return {
                "error": f"{operation} belongs to {correct}. "
                         f"Use {correct}() instead."
            }
        return {
            "error": f"Unknown operation: {operation}. "
                     "Use operation=\"help\" to list available operations."
        }

    fn = ops[operation]
    return _coerce_call(fn, params)


_HARDCODED_OPERATION = re.compile(r"""\boperation\s*=\s*["'](?![$<])""")


def _render_group_doc(group_name: str, doc: str, ops: dict) -> str:
    """Resolve $OpName placeholders in a group doc against the registered operations.

    Examples are hand-written while operation names are derived from the tool
    function names; rendering the names from the registry keeps the two from
    drifting apart, and an unresolved placeholder aborts startup. A hardcoded
    operation name is rejected outright; `<...>` stays available for deliberately
    generic placeholders.
    """
    if _HARDCODED_OPERATION.search(doc):
        raise RuntimeError(
            f"{group_name} doc hardcodes an operation name; use the $OpName form"
        )
    names = {name: name for name in ops} | {"help": "help"}
    try:
        return string.Template(doc).substitute(names)
    except (KeyError, ValueError) as exc:
        raise RuntimeError(
            f"{group_name} doc references an unknown operation placeholder: {exc}"
        ) from exc


# -- Registration -------------------------------------------------------------


def _register_tools():
    """Discover @_op-decorated functions, validate, and register as MCP tools."""
    groups: dict[str, tuple] = {}  # {group_name: (Group, {snake_name: fn})}

    for name, fn in inspect.getmembers(_tools_module, inspect.isfunction):
        if not hasattr(fn, "_mcp_group"):
            continue
        group = fn._mcp_group
        if group is ROOT:
            mcp.tool(structured_output=False)(_compact(_safe_tool(fn)))
        else:
            if group.name not in groups:
                groups[group.name] = (group, {})
            groups[group.name][1][name] = fn

    # Build operation maps and register meta-tools
    for group_name, (group, fns) in groups.items():
        ops = {_to_pascal(n): fn for n, fn in fns.items()}
        _group_ops[group_name] = ops
        doc = _render_group_doc(group_name, group.doc, ops)
        for pascal_name in ops:
            _all_grouped[pascal_name] = group_name

        def _make_tool(gname, gdoc):
            def tool_fn(operation: str, params: dict | None = None):
                params = params or {}
                if operation == "help":
                    return _build_help(gname)
                return _dispatch(operation, gname, params)
            tool_fn.__name__ = gname
            tool_fn.__qualname__ = gname
            tool_fn.__doc__ = gdoc
            return tool_fn

        mcp.tool(structured_output=False)(_compact(_safe_tool(_make_tool(group_name, doc))))


_register_tools()
