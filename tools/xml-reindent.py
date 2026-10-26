#!/usr/bin/python3
"""Normalise whitespace in Mapnik XML style and entity files.

- tabs are expanded (tab stop 8), trailing whitespace is removed,
  runs of trailing blank lines are reduced to a single final newline
- lines starting with a tag are indented by 2 spaces per nesting level
- continuation lines of a multi-line tag or comment are shifted by the
  same amount as the line the tag / comment started on, so attribute
  alignment is kept
- blocks of text content (e.g. SQL in <Parameter>) keep their relative
  indentation, the block as a whole is moved to the element's level
- CDATA sections are left alone

Only leading whitespace is changed, nothing is reflowed.

usage: xml-reindent.py [--check] file...
  --check  don't rewrite, list files that would change, exit 1 if any
"""
import sys

INDENT = 2

TEXT, TAG, COMMENT, CDATA, PI, DECL = range(6)


def scan(lines):
    """Return (state, depth, closing, text_end) for each line: state and
    depth at the start of the line, whether the line's first token is an
    end tag, and whether the line ends in element text content that
    started on it after a tag."""
    info = []
    state, depth = TEXT, 0
    quote = None          # quote char while inside an attribute value
    is_end = False        # current TAG is an end tag
    bracket = 0           # [ ] nesting inside <!DOCTYPE ...>
    for line in lines:
        s = line.lstrip()
        start = (state, depth, state == TEXT and s.startswith('</'))
        i, n = 0, len(line)
        tag_end = -1      # position after the last tag on this line
        while i < n:
            c = line[i]
            if state == TEXT:
                if c == '<':
                    if line.startswith('<!--', i):
                        state, i = COMMENT, i + 4
                        continue
                    if line.startswith('<![CDATA[', i):
                        state, i = CDATA, i + 9
                        continue
                    if line.startswith('<?', i):
                        state, i = PI, i + 2
                        continue
                    if line.startswith('<!', i):
                        state, bracket, i = DECL, 0, i + 2
                        continue
                    state, quote = TAG, None
                    is_end = line.startswith('</', i)
            elif state == TAG:
                if quote:
                    if c == quote:
                        quote = None
                elif c in '"\'':
                    quote = c
                elif c == '>':
                    if is_end:
                        depth -= 1
                    elif line[i - 1] != '/':
                        depth += 1
                    state, tag_end = TEXT, i + 1
            elif state == COMMENT:
                if line.startswith('-->', i):
                    state, i = TEXT, i + 3
                    continue
            elif state == CDATA:
                if line.startswith(']]>', i):
                    state, i = TEXT, i + 3
                    continue
            elif state == PI:
                if line.startswith('?>', i):
                    state, i = TEXT, i + 2
                    continue
            elif state == DECL:
                if quote:
                    if c == quote:
                        quote = None
                elif c in '"\'':
                    quote = c
                elif c == '[':
                    bracket += 1
                elif c == ']':
                    bracket -= 1
                elif c == '>' and bracket <= 0:
                    state = TEXT
            i += 1
        text_end = (state == TEXT and tag_end >= 0
                    and line[tag_end:].strip() != '')
        info.append(start + (text_end,))
    return info


def indent_of(line):
    return len(line) - len(line.lstrip(' '))


def reindent(text):
    lines = [l.expandtabs(8).rstrip() for l in text.split('\n')]
    info = scan(lines)
    out = []
    delta = 0
    text_cont = False     # inside element text that started after a tag
    i = 0
    while i < len(lines):
        line = lines[i]
        state, depth, closing, text_end = info[i]
        is_tag = line.lstrip().startswith('<')
        if not line:
            out.append('')
            i += 1
        elif state == CDATA:
            out.append(line)
            i += 1
        elif state != TEXT or (text_cont and not is_tag):
            # continuation of a tag, comment, declaration or PI,
            # or of element text that started after a tag on an earlier line
            out.append(' ' * max(0, indent_of(line) + delta) + line.lstrip())
            i += 1
        elif is_tag:
            new = INDENT * max(0, depth - 1 if closing else depth)
            delta = new - indent_of(line)
            out.append(' ' * new + line.lstrip())
            i += 1
        else:
            # block of text content lines, its first line is put on the
            # element's level, the others keep their relative indentation
            j = i
            while (j < len(lines) and info[j][0] == TEXT
                   and not lines[j].lstrip().startswith('<')):
                j += 1
            delta = INDENT * depth - indent_of(line)
            for l in lines[i:j]:
                out.append(' ' * max(0, indent_of(l) + delta) + l.lstrip() if l else '')
            i = j
            continue
        if text_end:
            text_cont = True
        elif state != TEXT or is_tag:
            text_cont = False
    while out and out[-1] == '':
        out.pop()
    return '\n'.join(out) + '\n'


def main(args):
    check = False
    if args and args[0] == '--check':
        check, args = True, args[1:]
    changed = []
    for f in args:
        with open(f, encoding='utf-8', newline='') as fh:
            old = fh.read()
        new = reindent(old.replace('\r\n', '\n'))
        if new != old:
            changed.append(f)
            if not check:
                with open(f, 'w', encoding='utf-8', newline='') as fh:
                    fh.write(new)
    for f in changed:
        print(f)
    return 1 if changed else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
