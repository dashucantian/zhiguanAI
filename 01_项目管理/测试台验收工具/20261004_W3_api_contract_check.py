#!/usr/bin/env python3
"""AI-014 / W3-DESKTOPOR-20261004-A: offline declared-route coverage audit.

Usage: python 20261004_W3_api_contract_check.py --root PROJECT [--json OUTPUT]
Exit 0: declaration coverage agrees; 1: differences/incomplete extraction;
2: input or syntax error. Only explicit input files are read. No production
imports, endpoint calls, directory scanning or data files. This is NOT runtime
registration, endpoint behavior, permissions or response-schema verification.
Supported: literal @app/@router HTTP decorators, websocket, api_route(methods=).
Nonliteral supported decorators, explicit include_router/mount/add_api_route,
and bare APIRouter(prefix=) are flagged. This is a bounded extractor, NOT a
complete detector of indirect registration, aliases or routes-list mutation.
Conditional declarations count regardless of reachability. The contract parser
supports the current Chinese section headings and simple pipe tables, not all
Markdown syntax. JSON is printed unless an output is requested.
"""
import argparse
import ast
import hashlib
import json
import re
import sys
from pathlib import Path

HTTP = {'get', 'post', 'put', 'patch', 'delete', 'head', 'options', 'trace'}
SOURCES = ('console_server.py', 'muse2-repo/muse2-master/nd_routes.py')
CONTRACT = '01_项目管理/20261004_驾驶舱前后端接口契约_v0.md'


def fingerprint(path):
    data = path.read_bytes()
    return data.decode('utf-8-sig'), hashlib.sha256(data).hexdigest()


def literal(node):
    return ast.literal_eval(node)


def extract(text, source):
    tree = ast.parse(text, filename=source)
    routes, issues = [], []
    decorators = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr in {'include_router', 'mount', 'add_api_route',
                                   'add_route', 'add_websocket_route'}:
                issues.append(f'{source}:{node.lineno}: manual registration/prefix requires review')
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id == 'APIRouter':
                for kw in node.keywords:
                    if kw.arg == 'prefix':
                        issues.append(f'{source}:{node.lineno}: APIRouter prefix requires review')
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for dec in node.decorator_list:
            if not isinstance(dec, ast.Call) or not isinstance(dec.func, ast.Attribute):
                continue
            kind = dec.func.attr
            if kind not in HTTP | {'websocket', 'api_route', 'route'}:
                continue
            receiver = dec.func.value
            if not isinstance(receiver, ast.Name) or receiver.id not in {'app', 'router'}:
                issues.append(f'{source}:{dec.lineno}: unsupported route receiver')
                continue
            try:
                path_node = dec.args[0] if dec.args else next(
                    kw.value for kw in dec.keywords if kw.arg == 'path')
                path = literal(path_node)
                if not isinstance(path, str) or not path.startswith('/'):
                    raise ValueError('literal absolute path required')
                if kind in {'api_route', 'route'}:
                    methods_node = next((kw.value for kw in dec.keywords
                                         if kw.arg == 'methods'), None)
                    methods = literal(methods_node) if methods_node else ['GET']
                    if not isinstance(methods, (list, tuple, set)) or not methods:
                        raise ValueError('nonempty literal methods required')
                    if any(not isinstance(m, str) or m.lower() not in HTTP for m in methods):
                        raise ValueError('unsupported HTTP method')
                    methods = sorted(set(m.upper() for m in methods))
                else:
                    methods = ['WS' if kind == 'websocket' else kind.upper()]
            except (ValueError, TypeError, StopIteration, SyntaxError):
                issues.append(f'{source}:{dec.lineno}: unresolved path/method declaration')
                continue
            if kind != 'websocket':
                decorators += 1
            for method in methods:
                routes.append({'method': method, 'path': path, 'source': source,
                               'line': dec.lineno, 'handler': node.name})
    return routes, decorators, issues


def parse_contract(text):
    """Read only the HTTP matrix and separate WS section, never prose mentions."""
    entries, issues, grouped = [], [], []
    section = None
    for number, line in enumerate(text.splitlines(), 1):
        if line.startswith('## '):
            section = ('http' if '契约矩阵' in line else
                       'ws' if 'WebSocket' in line else None)
        if not section or not line.lstrip().startswith('|'):
            continue
        cell = line.split('|')[1].replace('**', '').replace('`', '').strip()
        if section == 'http':
            match = re.fullmatch(r'(GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS|TRACE)\s+(.+)', cell)
            if not match:
                if '/' in cell:
                    issues.append(f'contract:{number}: unsupported HTTP row: {cell}')
                continue
            method, rest = match.groups()
            paths = rest.split()
            if any(not p.startswith('/') for p in paths):
                issues.append(f'contract:{number}: unsupported grouped paths: {cell}')
                continue
            if len(paths) > 1:
                grouped.append({'line': number, 'cell': cell})
        elif cell.startswith('/'):
            method, paths = 'WS', [cell]
            if ' ' in cell:
                issues.append(f'contract:{number}: unsupported WS row')
                continue
        else:
            continue
        entries.extend({'method': method, 'path': path, 'line': number} for path in paths)
    if not entries:
        issues.append('contract: no supported matrix entries')
    return entries, issues, grouped


def compare(routes, decorators, entries, issues, grouped):
    actual = {(r['method'], r['path']) for r in routes}
    documented = {(e['method'], e['path']) for e in entries}
    def names(keys):
        return [f'{method} {path}' for method, path in sorted(keys)]
    duplicate_source = {key for key in actual if sum(
        (r['method'], r['path']) == key for r in routes) > 1}
    duplicate_doc = {key for key in documented if sum(
        (e['method'], e['path']) == key for e in entries) > 1}
    http = {key for key in actual if key[0] != 'WS'}
    result = {
        'scope': 'static declarations only; not runtime/behavior/schema/privacy approval',
        'http_decorators': decorators, 'http_operations': len(http),
        'http_unique_paths': len({p for _, p in http}),
        'websocket_operations': len(actual - http),
        'documented_http_operations': len({k for k in documented if k[0] != 'WS'}),
        'missing_from_matrix': names(actual - documented),
        'not_in_source': names(documented - actual),
        'duplicate_source_operations': names(duplicate_source),
        'duplicate_matrix_operations': names(duplicate_doc),
        'extraction_issues': issues, 'grouped_rows': grouped,
        'routes': sorted(routes, key=lambda r: (r['method'], r['path'], r['source'], r['line'])),
    }
    result['ok'] = not any(result[k] for k in (
        'missing_from_matrix', 'not_in_source', 'duplicate_source_operations',
        'duplicate_matrix_operations', 'extraction_issues'))
    return result


def audit(root, source_names=SOURCES, contract_name=CONTRACT):
    root = Path(root).resolve()
    routes, count, issues, inputs = [], 0, [], []
    for name in source_names:
        path = (root / name).resolve()
        path.relative_to(root)
        text, digest = fingerprint(path)
        found, n, problems = extract(text, name)
        routes.extend(found)
        count += n
        issues.extend(problems)
        inputs.append({'path': name, 'sha256': digest})
    contract_path = (root / contract_name).resolve()
    contract_path.relative_to(root)
    text, digest = fingerprint(contract_path)
    entries, problems, grouped = parse_contract(text)
    issues.extend(problems)
    result = compare(routes, count, entries, issues, grouped)
    result['inputs'] = inputs + [{'path': contract_name, 'sha256': digest}]
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', required=True, type=Path)
    parser.add_argument('--json', type=Path, help='new output file; never overwrite inputs/existing files')
    args = parser.parse_args()
    try:
        result = audit(args.root)
        payload = json.dumps(result, ensure_ascii=False, indent=2) + '\n'
        if args.json:
            with args.json.open('x', encoding='utf-8') as out:
                out.write(payload)
        else:
            print(payload, end='')
        return 0 if result['ok'] else 1
    except (OSError, SyntaxError, ValueError) as error:
        print(f'input/output error: {error}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
