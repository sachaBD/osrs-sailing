"""Best-effort static check of the browser JS: bracket balance + DOM ids.

There is no JS runtime available here, so this is a smoke test, not a parser.
"""
import re, sys

REGEX_LITERAL = re.compile(
    r'(?:(?<=[(,=:!&|?{;\[])|(?<=\breturn)|(?<=\bcase)|(?<=\btypeof)|(?<==>))'
    r'\s*/(?![/*])(?:\\.|\[(?:\\.|[^\]\\])*\]|[^/\\\n])+/[gimsuy]*')


def strip_js(src):
    """Remove strings, comments and regex literals, keeping only structural brackets.

    Template literals nest (`a ${ f(`b`) } c`), so this walks a small stack:
    inside a template only ${ ... } is code, and inside that code a further
    template can open again.
    """
    src = REGEX_LITERAL.sub(' RE ', src)
    out = []
    stack = ['code']          # 'code' | 'tmpl'
    depth = []                # brace depth at each ${ we entered
    braces = 0
    i, n = 0, len(src)
    while i < n:
        c = src[i]
        if stack[-1] == 'tmpl':
            if c == '\\':
                i += 2; continue
            if c == '`':
                stack.pop(); i += 1; continue
            if c == '$' and src.startswith('${', i):
                stack.append('code'); depth.append(braces)
                out.append('{'); braces += 1; i += 2; continue
            i += 1; continue

        if c in '"\'':
            q, i = c, i + 1
            while i < n and src[i] != q:
                i += 2 if src[i] == '\\' else 1
            i += 1; continue
        if c == '`':
            stack.append('tmpl'); i += 1; continue
        if src.startswith('//', i):
            j = src.find('\n', i)
            if j < 0: break
            i = j; continue
        if src.startswith('/*', i):
            i = src.find('*/', i) + 2; continue
        if c == '{':
            braces += 1
        elif c == '}':
            braces -= 1
            if len(stack) > 1 and depth and braces == depth[-1]:
                # this } closes a ${ ... } hole, so drop back into the template
                depth.pop(); stack.pop()
                out.append('}'); i += 1; continue
        out.append(c)
        i += 1
    return ''.join(out)


def main():
    ok = True
    for f in ['app.js', 'map.js']:
        src = strip_js(open(f).read())
        for a, b in [('{', '}'), ('(', ')'), ('[', ']')]:
            if src.count(a) != src.count(b):
                ok = False
                print(f'  {f}: UNBALANCED {a}{b} -> {src.count(a)} vs {src.count(b)}')
        print(f'  {f}: ok' if ok else f'  {f}: see above')

    html = open('index.html').read()
    ids = set(re.findall(r'\bid="([^"]+)"', html))
    refs = set()
    for f in ['app.js', 'map.js']:
        js = open(f).read()
        refs |= set(re.findall(r"querySelector\('#([^']+)'\)", js))
        refs |= set(re.findall(r"\$\('#([^']+)'\)", js))
    missing = sorted(r for r in refs if r not in ids)
    if missing:
        ok = False
        print(f'  MISSING DOM ids: {missing}')
    else:
        print(f'  DOM ids: {len(refs)} referenced, all present')

    scripts = re.findall(r'<script src="([^"]+)"', html)
    print(f'  script order: {scripts}')
    print('STATIC CHECK:', 'pass' if ok else 'FAIL')
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
