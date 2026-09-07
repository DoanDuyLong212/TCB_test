"""Table helpers: markdown conversion preserving Vietnamese number formats."""


def to_markdown(rows: list[list]) -> str:
    """Convert row matrix to pipe markdown. Never normalize ',' '.' or units."""
    clean = [[("" if c is None else str(c)).strip() for c in r] for r in rows]
    if not clean:
        return ""
    width = max(len(r) for r in clean)
    clean = [r + [""] * (width - len(r)) for r in clean]
    header, body = clean[0], clean[1:]
    lines = ["| " + " | ".join(header) + " |"]
    lines.append("| " + " | ".join(["---"] * width) + " |")
    for r in body:
        lines.append("| " + " | ".join(r) + " |")
    return "\n".join(lines)
