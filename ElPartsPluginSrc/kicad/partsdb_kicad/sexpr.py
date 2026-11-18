"""Small, strict S-expression reader; never executes source text."""
import re

from ElPartsPluginApi.importers import InvalidSourceError

_TOKEN = re.compile(r'\s+|\(|\)|"(?:\\.|[^"\\])*"|[^\s()"]+')


def parse(text):
    stack = []
    root = None
    end = 0
    for match in _TOKEN.finditer(text):
        if match.start() != end:
            raise InvalidSourceError('Invalid S-expression token')
        end = match.end()
        token = match.group()
        if token.isspace():
            continue
        if token == '(':
            node = []
            if stack:
                stack[-1].append(node)
            elif root is not None:
                raise InvalidSourceError('Multiple S-expression roots')
            else:
                root = node
            stack.append(node)
        elif token == ')':
            if not stack:
                raise InvalidSourceError('Unexpected closing parenthesis')
            stack.pop()
        else:
            if not stack:
                raise InvalidSourceError('Value outside S-expression')
            if token.startswith('"'):
                token = re.sub(r'\\(.)', lambda m: {'n': '\n', 'r': '\r', 't': '\t',
                               '"': '"', '\\': '\\'}.get(m[1], '\\' + m[1]), token[1:-1])
            stack[-1].append(token)
    if end != len(text) or stack or not root:
        raise InvalidSourceError('Incomplete S-expression')
    return root


def children(node, key):
    return [item for item in node if isinstance(item, list) and item and item[0] == key]


def first(node, key):
    return next(iter(children(node, key)), [])


def value(node, key, default=''):
    item = first(node, key)
    return item[1] if len(item) > 1 else default


def properties(node):
    return {item[1]: item[2] for item in children(node, 'property') if len(item) >= 3}
