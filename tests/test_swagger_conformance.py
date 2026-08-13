"""Conformance check: every hand-written API call matches Casdoor's swagger spec.

Casdoor is a Go/Beego service that reads request fields by name and drops
anything it does not recognise, so a wrong wire name is invisible: the call
still returns 200 and the field simply never applies. Casdoor also keeps
resource identity in the query string rather than the path (`POST
/api/update-role?id=owner/name`), so *omitting* a required query param fails the
same silent way - the handler resolves an empty id, changes nothing, and still
answers 200. Neither the type system nor a smoke test can see either class of
bug, so this test reads every registered op in `casdoor_mcp.tools` off its own
AST and asserts each call's method, path, query-param names and body-field names
against Casdoor's own spec.

Spec provenance: `casdoor-swagger.json` next to this file is a byte-for-byte
copy of

    https://raw.githubusercontent.com/casdoor/casdoor/v3.152.0/swagger/swagger.json

It is vendored rather than fetched because this repo's `dev.py check` (and the
pre-commit hook behind it) runs the whole suite, which must stay offline and
deterministic, and because a bump then shows up as a reviewable diff. Refresh it
by re-running that curl against a newer tag and updating `_SPEC_TAG`.

Two checks the Gitea sibling of this test carries are deliberately absent
because Casdoor's surface makes them dead code, and each is replaced by a guard
that fails once the assumption stops holding:

- structural path-placeholder matching: Casdoor's API is flat RPC-style, and
  none of the paths we call is templated (see `test_wire_calls_match_swagger`);
- Literal-vs-enum comparison: the spec declares no enum on any endpoint we call
  (see `test_spec_declares_no_enums_on_endpoints_we_call`).

Known limitation: names reaching the wire through an op's `**kwargs` are not
checked, because they are chosen by the caller at runtime. A caller that passes
a field literally named `kwargs` lands it in the body as an unchecked wire name;
that is dispatch's shape, not something this test can see.
"""

from __future__ import annotations

import ast
import functools
import inspect
import json
import re
import sys
import textwrap
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from casdoor_mcp import server, tools

_SPEC_TAG = "v3.152.0"
_SPEC_PATH = Path(__file__).parent / "casdoor-swagger.json"

# Ops whose call shape the extractor below cannot read. ONLY code shapes belong
# here - never a name mismatch, which is the whole point of this test.
UNANALYZABLE_OK: dict[str, str] = {}

# Ops with no wire call of their own: they only drive other registered ops,
# whose calls are checked in their own right.
NO_WIRE_CALL_OK: frozenset[str] = frozenset()

# Ops whose endpoint is deliberately absent from the pinned spec.
# Reviewed entries only; the conformance test fails if the endpoint reappears.
SPEC_GAPS: dict[str, str] = {}

# Query params the spec marks required that the handler in fact treats as
# optional. Casdoor's swagger is generated from hand-written Beego annotations,
# so `required` is a claim about intent, not about the code; every entry here
# was checked against the controller source at _SPEC_TAG.
# Each entry names the endpoint it waives, so retargeting an op at a different
# endpoint retires the waiver instead of silently carrying it over.
SPEC_OVERCLAIMS: dict[str, tuple[str, str, frozenset[str]]] = {
    # GetOrganizations: an empty owner lists every organization, which is
    # exactly what list_organizations() promises.
    "list_organizations": ("GET", "/api/get-organizations", frozenset({"owner"})),
    # GetTokens: empty pageSize/p is the documented "no pagination" branch and
    # returns the full list.
    "list_tokens": ("GET", "/api/get-tokens", frozenset({"pageSize", "p"})),
}


_CLIENT_VERBS = {"get": "GET", "post": "POST"}

# Client kwargs that carry no request-payload names.
_NO_PAYLOAD_KWARGS = frozenset({"headers", "timeout"})

# Call plumbing the extractor already models; everything else that reaches
# these markers inside a helper is a wire call hiding from the check.
_PLUMBING = frozenset({"_get_client"})
_WIRE_MARKER = re.compile(r"_get_client\(|httpx\.")

_PLACEHOLDER = re.compile(r"\{\w+\}")

# Helper whose result is the object Casdoor itself just returned.
_MERGE_HELPER = "_merged"


@functools.cache
def _hits_wire(target: Callable[..., Any]) -> bool:
    """True if `target` reaches the wire, directly or through another helper.

    Transitive on purpose: every op in this module hands its response to a
    helper (`_ok`, `_data`, `_slim_list`), so a depth-1 check would let a call
    one level further down hide from the extractor completely.
    """
    return _reaches_wire(target, frozenset())


def _reaches_wire(target: Callable[..., Any], seen: frozenset[str]) -> bool:
    """Walk plain-name calls from `target`, resolving each in its own module.

    Known blind spot: attribute calls (`mod.helper()`, `obj.method()`) are not
    followed. Every helper in this package is a module-level function called by
    bare name, so the walk is complete today; a helper reached through an
    attribute would need this to grow a resolver.
    """
    # getsource failing here is a loud test error by design: an unreadable
    # helper cannot be assumed clean.
    source = inspect.getsource(target)
    if _WIRE_MARKER.search(source):
        return True
    module = sys.modules.get(target.__module__)
    seen = seen | {f"{target.__module__}.{target.__qualname__}"}
    for node in ast.walk(ast.parse(textwrap.dedent(source))):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)):
            continue
        callee = getattr(module, node.func.id, None)
        if not inspect.isfunction(callee):
            continue
        # Registered ops are checked in their own right, cycles end the walk.
        key = f"{callee.__module__}.{callee.__qualname__}"
        if key in seen or hasattr(callee, "_mcp_group"):
            continue
        if _reaches_wire(callee, seen):
            return True
    return False


@dataclass(frozen=True)
class _WireCall:
    """One outbound HTTP call, as read off the source of an op."""

    method: str
    path: str
    query: frozenset[str]
    body: frozenset[str]


# Stand-in for a call the extractor gave up on; dropped with the rest once the
# op is marked unreadable.
_UNREADABLE = _WireCall("", "", frozenset(), frozenset())


def _is_named(node: ast.expr | None, name: str | None) -> bool:
    return name is not None and isinstance(node, ast.Name) and node.id == name


def _is_call_to(node: ast.expr | None, name: str) -> bool:
    return isinstance(node, ast.Call) and _is_named(node.func, name)


# -- AST extraction ---------------------------------------------------------


class _OpExtractor:
    """Reads the wire calls an op makes straight off its source.

    Every shape outside the grammar records a reason in `blocked` and the op is
    reported as unanalyzable rather than half-checked.
    """

    def __init__(self, fn: Callable[..., Any]) -> None:
        self.var_keyword = next(
            (
                p.name
                for p in inspect.signature(fn).parameters.values()
                if p.kind is inspect.Parameter.VAR_KEYWORD
            ),
            None,
        )
        tree = ast.parse(textwrap.dedent(inspect.getsource(fn)))
        self.stmts: list[ast.stmt] = tree.body[0].body  # type: ignore[attr-defined]
        self.blocked: str | None = None

    def calls(self) -> list[_WireCall]:
        found = []
        for node in self._walk():
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            if isinstance(fn, ast.Attribute) and _is_call_to(fn.value, "_get_client"):
                found.append(self._from_client(node, fn.attr))
            elif isinstance(fn, ast.Name):
                self._check_helper(fn.id)
        return [] if self.blocked else found

    def _check_helper(self, name: str) -> None:
        """Block ops whose helpers hit the wire where this test cannot see."""
        if name in _PLUMBING:
            return
        target = getattr(tools, name, None)
        # Registered ops another op drives are checked in their own right.
        if not inspect.isfunction(target) or hasattr(target, "_mcp_group"):
            return
        if _hits_wire(target):
            self._block(f"calls {name}(), which makes HTTP calls this extractor cannot read")

    def _walk(self) -> Iterator[ast.AST]:
        for stmt in self.stmts:
            yield from ast.walk(stmt)

    def _block(self, reason: str) -> None:
        if self.blocked is None:
            self.blocked = reason

    # -- literals -----------------------------------------------------------

    def _const_str(self, node: ast.expr | None) -> str:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        self._block(f"expected a string literal, found {type(node).__name__}")
        return ""

    def _dict_keys(self, node: ast.Dict) -> set[str]:
        names: set[str] = set()
        for key, value in zip(node.keys, node.values):
            if key is None:
                self._check_open_spread(value)
                continue
            names.add(self._const_str(key))
        return names

    def _check_open_spread(self, value: ast.expr | None) -> None:
        """Allow the two spreads whose names cannot come from our source.

        `**kwargs` forwards caller-supplied Casdoor fields and `**_merged(...)`
        re-sends the object Casdoor itself just returned, so neither carries a
        hand-written wire name for this test to check - and neither hides one.
        Any other `**` could smuggle names onto the wire.
        """
        if _is_named(value, self.var_keyword) or _is_call_to(value, _MERGE_HELPER):
            return
        self._block(f"dict literal unpacks something other than **kwargs or {_MERGE_HELPER}()")

    # -- name derivation ----------------------------------------------------

    def _payload_names(self, value: ast.expr | None) -> set[str]:
        if value is None or (isinstance(value, ast.Constant) and value.value is None):
            return set()
        if isinstance(value, ast.Dict):
            return self._dict_keys(value)
        if isinstance(value, ast.Name):
            return self._resolve_dict_var(value.id)
        self._block(f"payload is a {type(value).__name__}, not a readable dict")
        return set()

    def _resolve_dict_var(self, name: str) -> set[str]:
        """Union of the keys a local dict variable can end up carrying."""
        keys: set[str] = set()
        assigned = False
        for node in self._walk():
            targets: list[ast.expr] = []
            value: ast.expr | None = None
            if isinstance(node, ast.Assign):
                targets, value = list(node.targets), node.value
            elif isinstance(node, ast.AnnAssign):
                targets, value = [node.target], node.value
            elif isinstance(node, ast.AugAssign) and _is_named(node.target, name):
                self._block(f"augmented assignment to {name!r}")
            elif isinstance(node, ast.Delete) and any(
                isinstance(t, ast.Subscript) and _is_named(t.value, name) for t in node.targets
            ):
                self._block(f"del {name}[...] drops a field this test would still count")
            elif (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and _is_named(node.func.value, name)
            ):
                self._block(f"{name}.{node.func.attr}() mutates the payload")
            for target in targets:
                if _is_named(target, name):
                    keys |= self._initial_keys(value)
                    assigned = True
                elif isinstance(target, ast.Subscript) and _is_named(target.value, name):
                    keys.add(self._const_str(target.slice))
        if not assigned:
            self._block(f"no assignment to {name!r} found in the op")
        return keys

    def _initial_keys(self, value: ast.expr | None) -> set[str]:
        if isinstance(value, ast.Dict):
            return self._dict_keys(value)
        self._block(f"dict built from a {type(value).__name__}, not a literal")
        return set()

    # -- call shapes --------------------------------------------------------

    def _from_client(self, node: ast.Call, verb: str) -> _WireCall:
        method = _CLIENT_VERBS.get(verb)
        if method is None:
            self._block(f"unknown client method {verb!r}")
            return _UNREADABLE
        if len(node.args) != 1:
            self._block(f"{verb}() is not called as {verb}(path, ...)")
            return _UNREADABLE
        path = self._const_str(node.args[0])
        query: set[str] = set()
        body: set[str] = set()
        for kw in node.keywords:
            if kw.arg == "params":
                query |= self._payload_names(kw.value)
            elif kw.arg == "json":
                body |= self._payload_names(kw.value)
            elif kw.arg not in _NO_PAYLOAD_KWARGS:
                self._block(f"{verb}() carries a payload in {kw.arg!r}")
        return _WireCall(method, path, frozenset(query), frozenset(body))


@dataclass(frozen=True)
class _Ops:
    analyzed: dict[str, list[_WireCall]]
    unanalyzable: dict[str, str]
    no_wire_call: list[str]


@functools.lru_cache(maxsize=1)
def _extract_ops() -> _Ops:
    analyzed: dict[str, list[_WireCall]] = {}
    unanalyzable: dict[str, str] = {}
    no_wire_call: list[str] = []
    members = inspect.getmembers(
        tools, lambda o: inspect.isfunction(o) and hasattr(o, "_mcp_group")
    )
    for name, fn in sorted(members):
        extractor = _OpExtractor(fn)
        calls = extractor.calls()
        if extractor.blocked:
            unanalyzable[name] = extractor.blocked
        elif calls:
            analyzed[name] = calls
        else:
            no_wire_call.append(name)
    return _Ops(analyzed, unanalyzable, no_wire_call)


# -- Swagger index ----------------------------------------------------------


@dataclass(frozen=True)
class _Endpoint:
    query: frozenset[str]
    required_query: frozenset[str]
    body: frozenset[str]
    enum_query: frozenset[str]


class _Swagger:
    """Accepted query/body names per (path, method), read off the pinned spec."""

    def __init__(self, spec: dict[str, Any]) -> None:
        self._defs: dict[str, Any] = spec.get("definitions") or {}
        self.endpoints: dict[tuple[str, str], _Endpoint] = {}
        self.paths: frozenset[str] = frozenset(spec["paths"])
        for path, item in spec["paths"].items():
            for method, operation in item.items():
                if isinstance(operation, dict):
                    self.endpoints[path, method.upper()] = self._endpoint(operation)

    def _endpoint(self, operation: dict[str, Any]) -> _Endpoint:
        query: set[str] = set()
        required: set[str] = set()
        body: set[str] = set()
        enums: set[str] = set()
        for param in operation.get("parameters") or []:
            where = param.get("in")
            if where == "query":
                query.add(param["name"])
                if param.get("required"):
                    required.add(param["name"])
                # Formal enums only; prose-documented value sets are not
                # machine-checkable and are skipped.
                if param.get("enum") or (param.get("items") or {}).get("enum"):
                    enums.add(param["name"])
            elif where == "formData":
                body.add(param["name"])
            elif where == "body":
                body |= self._properties(param.get("schema") or {})
        return _Endpoint(
            frozenset(query), frozenset(required), frozenset(body), frozenset(enums)
        )

    def _properties(self, schema: dict[str, Any], depth: int = 0) -> set[str]:
        if depth > 8 or not isinstance(schema, dict):
            return set()
        ref = schema.get("$ref")
        if ref:
            return self._properties(self._defs.get(ref.rsplit("/", 1)[-1]) or {}, depth + 1)
        names = set(schema.get("properties") or {})
        for member in schema.get("allOf") or []:
            names |= self._properties(member, depth + 1)
        return names

    def describe_path(self, path: str) -> str:
        methods = sorted(m for (p, m) in self.endpoints if p == path)
        return f"the spec has {methods} for it" if methods else "the spec has no such path"


@pytest.fixture(scope="session")
def swagger() -> _Swagger:
    spec = json.loads(_SPEC_PATH.read_text(encoding="utf-8"))
    # A truncated or wrong file would otherwise read as "every endpoint is
    # missing" - one clear failure beats one per op.
    assert spec.get("swagger") == "2.0" and spec.get("paths"), (
        f"{_SPEC_PATH.name} is not a swagger 2.0 document; re-fetch it from the "
        f"Casdoor tree at {_SPEC_TAG}"
    )
    return _Swagger(spec)


def _waived(op: str, call: _WireCall) -> frozenset[str]:
    """Params waived for this op, but only on the endpoint the waiver names."""
    entry = SPEC_OVERCLAIMS.get(op)
    if entry is None or (entry[0], entry[1]) != (call.method, call.path):
        return frozenset()
    return entry[2]


def _checked_calls() -> Iterator[tuple[str, _WireCall]]:
    """Every analyzed call whose endpoint is expected to be in the spec."""
    for op, calls in sorted(_extract_ops().analyzed.items()):
        if op not in SPEC_GAPS:
            yield from ((op, call) for call in calls)


# -- Tests ------------------------------------------------------------------


def test_every_exposed_operation_is_checked() -> None:
    """Ops are discovered by an attribute, so renaming the registry marker would
    silently empty this whole suite. Anchor discovery to what the server exposes."""
    ops = _extract_ops()
    discovered = set(ops.analyzed) | set(ops.unanalyzable) | set(ops.no_wire_call)
    covered = {server._to_pascal(name) for name in discovered}
    exposed = {op for group in server._group_ops.values() for op in group}
    missing = sorted(exposed - covered)
    assert exposed and not missing, (
        f"{len(missing)} operation(s) the server exposes are invisible to this "
        f"conformance test: {missing}"
    )


def test_every_unanalyzable_op_is_allowlisted() -> None:
    unknown = {
        name: reason
        for name, reason in _extract_ops().unanalyzable.items()
        if name not in UNANALYZABLE_OK
    }
    assert not unknown, (
        "Ops whose calls this test cannot read are missing from UNANALYZABLE_OK. "
        "Reshape the op into a readable form, teach the extractor the shape, or "
        "allowlist it - code shapes only, NEVER a name mismatch:\n"
        + "\n".join(f"  {name}: {reason}" for name, reason in sorted(unknown.items()))
    )


def test_allowlist_has_no_stale_entries() -> None:
    stale = sorted(set(UNANALYZABLE_OK) - set(_extract_ops().unanalyzable))
    assert not stale, (
        "These ops are analyzable now - drop them from UNANALYZABLE_OK so the "
        f"allowlist can only shrink: {stale}"
    )
    orphaned = sorted(set(SPEC_GAPS) - set(_extract_ops().analyzed))
    assert not orphaned, f"SPEC_GAPS names ops with no analyzed wire call: {orphaned}"


def test_no_wire_call_ops_are_expected() -> None:
    ops = _extract_ops()
    unexpected = sorted(set(ops.no_wire_call) - NO_WIRE_CALL_OK)
    assert not unexpected, (
        "Ops with no readable wire call of their own. If they truly only "
        f"drive other registered ops, add them to NO_WIRE_CALL_OK: {unexpected}"
    )
    stale = sorted(NO_WIRE_CALL_OK - set(ops.no_wire_call))
    assert not stale, f"NO_WIRE_CALL_OK entries no longer match reality: {stale}"


def test_spec_declares_no_enums_on_endpoints_we_call(swagger: _Swagger) -> None:
    """Guard for a check this module does not carry.

    Casdoor's spec declares no enum anywhere, so there is nothing to compare a
    `Literal` annotation against and no such check exists here. If an endpoint
    we call ever grows one, write it: a Literal value the enum lacks is the same
    silent-lie class, with Casdoor falling back to its default.
    """
    found = []
    for _, call in _checked_calls():
        endpoint = swagger.endpoints.get((call.path, call.method))
        if endpoint is not None and endpoint.enum_query:
            found.append(f"{call.method} {call.path}: {sorted(endpoint.enum_query)}")
    assert not found, (
        "The spec now declares query enums on endpoints we call; add a "
        "Literal-vs-enum check for them:\n" + "\n".join(f"  {f}" for f in found)
    )


def test_spec_overclaims_are_not_stale(swagger: _Swagger) -> None:
    findings: list[str] = []
    for op, (method, path, params) in sorted(SPEC_OVERCLAIMS.items()):
        calls = [
            c
            for c in _extract_ops().analyzed.get(op, [])
            if (c.method, c.path) == (method, path)
        ]
        if not calls:
            findings.append(f"{op}: no longer calls the waived {method} {path}")
            continue
        required: set[str] = set()
        sent: set[str] = set()
        for call in calls:
            endpoint = swagger.endpoints.get((call.path, call.method))
            required |= endpoint.required_query if endpoint else frozenset()
            sent |= call.query
        for param in sorted(params - required):
            findings.append(f"{op}.{param}: the spec no longer marks it required")
        for param in sorted(params & sent):
            findings.append(f"{op}.{param}: the op sends it now, so the waiver is dead")
    assert not findings, (
        "SPEC_OVERCLAIMS entries no longer describe reality; drop them so the "
        "waiver list can only shrink:\n" + "\n".join(f"  {f}" for f in findings)
    )


def test_required_query_params_are_sent(swagger: _Swagger) -> None:
    """Casdoor keeps resource identity in the query string, so a required query
    param we never send is the same silent failure as a misspelled one: the
    handler resolves an empty value, does nothing, and still returns 200."""
    findings: list[str] = []
    for op, call in _checked_calls():
        endpoint = swagger.endpoints.get((call.path, call.method))
        if endpoint is None:
            continue  # reported by test_wire_calls_match_swagger
        missing = sorted(endpoint.required_query - call.query - _waived(op, call))
        if missing:
            findings.append(
                f"{op}: {call.method} {call.path} never sends required query "
                f"params {missing}"
            )
    assert not findings, (
        f"{len(findings)} call(s) omit a query param the spec marks required. "
        "Send it, or - if Casdoor's handler really treats it as optional - add "
        "it to SPEC_OVERCLAIMS with the controller source as justification:\n"
        + "\n".join(f"  {f}" for f in findings)
    )


def test_wire_calls_match_swagger(swagger: _Swagger) -> None:
    findings: list[str] = []
    for op, calls in sorted(_extract_ops().analyzed.items()):
        for call in calls:
            where = f"{op}: {call.method} {call.path}"
            known = (call.path, call.method) in swagger.endpoints
            if op in SPEC_GAPS:
                if known:
                    findings.append(
                        f"{where}: endpoint is back in the spec - drop it from SPEC_GAPS"
                    )
                continue
            if not known:
                hint = (
                    " (paths are matched exactly; a templated path needs a "
                    "placeholder matcher this module does not carry)"
                    if _PLACEHOLDER.search(call.path)
                    else ""
                )
                findings.append(
                    f"{where}: no such endpoint - {swagger.describe_path(call.path)}{hint}"
                )
                continue
            endpoint = swagger.endpoints[call.path, call.method]
            bad_query = sorted(call.query - endpoint.query)
            if bad_query:
                findings.append(
                    f"{where}: query params {bad_query} are not in the spec; "
                    f"it accepts {sorted(endpoint.query)}"
                )
            bad_body = sorted(call.body - endpoint.body)
            if bad_body:
                findings.append(
                    f"{where}: body fields {bad_body} are not in the spec; "
                    f"it accepts {sorted(endpoint.body)}"
                )
    assert not findings, (
        f"{len(findings)} call(s) disagree with the Casdoor spec. Casdoor drops "
        "unknown names silently, so each of these is a request that quietly "
        "does not do what it says:\n" + "\n".join(f"  {f}" for f in findings)
    )
