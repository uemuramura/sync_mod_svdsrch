"""Extract SPL from Markdown using a documented priority order."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

SPL_LANGUAGES = frozenset({"spl", "splunk", "splunk-spl", "splunkql"})
MAIN_LANGUAGES = frozenset({"spl-main", "splunk-main"})
HEADING_NAMES = frozenset(
    {
        "search",
        "saved search",
        "savedsearch",
        "spl",
        "サーチ",
        "検索",
    }
)

FRONTMATTER_RE = re.compile(r"\A---[ \t]*\r?\n(.*?\r?\n)---[ \t]*\r?\n?", re.DOTALL)
COMMENT_START_RE = re.compile(r"<!--\s*spl:start\s*-->", re.IGNORECASE)
COMMENT_END_RE = re.compile(r"<!--\s*spl:end\s*-->", re.IGNORECASE)
FENCE_OPEN_RE = re.compile(r"^([`~]{3,})([^`]*)$")
HEADING_RE = re.compile(r"^(#{1,6})[ \t]+(.+?)[ \t]*#*[ \t]*$")

BOOL_TRUE = frozenset({"true", "yes", "on", "1"})
BOOL_FALSE = frozenset({"false", "no", "off", "0"})

INTERNAL_META_KEYS = frozenset(
    {"skip", "search_name", "combine_spl_blocks", "search"}
)


@dataclass
class Fence:
    language: str
    flags: List[str]
    body: str
    start_line: int


@dataclass
class ParseResult:
    ok: bool
    spl: str = ""
    source: str = ""
    search_name: Optional[str] = None
    skip: bool = False
    combine_spl_blocks: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)
    error: str = ""
    warning: str = ""


def extract_spl(markdown: str) -> ParseResult:
    """Return the canonical SPL payload for one Markdown document."""
    if markdown is None:
        return ParseResult(ok=False, error="empty_document")
    text = markdown.lstrip("\ufeff")
    meta, body = _parse_frontmatter(text)
    skip = _as_bool(meta.get("skip", False))
    combine = _as_bool(meta.get("combine_spl_blocks", False))
    search_name = _optional_str(meta.get("search_name"))
    saved_meta = _public_metadata(meta)

    if skip:
        return ParseResult(
            ok=True,
            skip=True,
            search_name=search_name,
            combine_spl_blocks=combine,
            metadata=saved_meta,
            source="frontmatter.skip",
        )

    fm_search = meta.get("search")
    if isinstance(fm_search, str) and fm_search.strip():
        return _finish(
            fm_search.strip(),
            "frontmatter.search",
            search_name,
            combine,
            saved_meta,
        )

    fences = _parse_fences(body)
    spl_fences = [item for item in fences if _is_spl_fence(item)]
    main_fences = [item for item in fences if _is_main_fence(item)]

    if len(main_fences) == 1:
        return _finish(
            main_fences[0].body,
            "fence.spl-main",
            search_name,
            combine,
            saved_meta,
        )
    if len(main_fences) > 1:
        return ParseResult(ok=False, error="multiple_spl_main_blocks")

    comment_regions = _extract_comment_regions(body)
    if len(comment_regions) == 1:
        return _finish(
            comment_regions[0],
            "html_comment",
            search_name,
            combine,
            saved_meta,
        )
    if len(comment_regions) > 1:
        if combine:
            return _finish(
                "\n\n".join(comment_regions),
                "html_comment.combined",
                search_name,
                combine,
                saved_meta,
            )
        return ParseResult(ok=False, error="multiple_spl_comment_regions")

    if len(spl_fences) == 1:
        return _finish(
            spl_fences[0].body,
            "fence.spl",
            search_name,
            combine,
            saved_meta,
        )
    if len(spl_fences) > 1:
        if combine:
            return _finish(
                "\n\n".join(item.body for item in spl_fences),
                "fence.spl.combined",
                search_name,
                combine,
                saved_meta,
            )
        return ParseResult(ok=False, error="multiple_spl_blocks")

    heading_spl = _extract_heading_fence(body)
    if heading_spl:
        return _finish(
            heading_spl, "heading", search_name, combine, saved_meta
        )

    if len(fences) == 1 and fences[0].body.strip():
        return _finish(
            fences[0].body,
            "fence.unlabeled",
            search_name,
            combine,
            saved_meta,
            warning="unlabeled_fence",
        )

    return ParseResult(ok=False, error="no_spl_found")


def _finish(
    spl: str,
    source: str,
    search_name: Optional[str],
    combine: bool,
    metadata: Dict[str, Any],
    warning: str = "",
) -> ParseResult:
    cleaned = spl.strip()
    if not cleaned:
        return ParseResult(ok=False, error="empty_spl")
    return ParseResult(
        ok=True,
        spl=cleaned,
        source=source,
        search_name=search_name,
        combine_spl_blocks=combine,
        metadata=metadata,
        warning=warning,
    )


def _parse_frontmatter(text: str) -> Tuple[Dict[str, Any], str]:
    match = FRONTMATTER_RE.match(text)
    if not match:
        return {}, text
    return _parse_simple_yaml(match.group(1)), text[match.end() :]


def _parse_simple_yaml(raw: str) -> Dict[str, Any]:
    result = {}  # type: Dict[str, Any]
    lines = raw.splitlines()
    index = 0
    while index < len(lines):
        line = lines[index]
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            index += 1
            continue
        if ":" not in line:
            index += 1
            continue
        key, _, rest = line.partition(":")
        key = key.strip()
        rest = rest.strip()
        if not key:
            index += 1
            continue
        if rest in ("|", ">", "|-", ">-"):
            indent_base = None
            chunks = []  # type: List[str]
            index += 1
            while index < len(lines):
                nxt = lines[index]
                if not nxt.strip():
                    chunks.append("")
                    index += 1
                    continue
                leading = len(nxt) - len(nxt.lstrip(" "))
                if indent_base is None:
                    if leading == 0:
                        break
                    indent_base = leading
                if leading < indent_base:
                    break
                chunks.append(nxt[indent_base:])
                index += 1
            result[key] = "\n".join(chunks).strip("\n")
            continue
        result[key] = _coerce_yaml_value(_unquote(rest))
        index += 1
    return result


def _parse_fences(text: str) -> List[Fence]:
    fences = []  # type: List[Fence]
    lines = text.splitlines()
    index = 0
    while index < len(lines):
        opened = FENCE_OPEN_RE.match(lines[index])
        if not opened:
            index += 1
            continue
        marker = opened.group(1)
        info = opened.group(2).strip()
        char = marker[0]
        length = len(marker)
        body_lines = []  # type: List[str]
        index += 1
        start_line = index
        found = False
        close_re = re.compile("^" + re.escape(char) + "{" + str(length) + r",}\s*$")
        while index < len(lines):
            if close_re.match(lines[index]):
                found = True
                break
            body_lines.append(lines[index])
            index += 1
        if found:
            tokens = info.split()
            language = tokens[0].lower() if tokens else ""
            flags = [token.lower() for token in tokens[1:]]
            fences.append(
                Fence(
                    language=language,
                    flags=flags,
                    body="\n".join(body_lines).strip("\n"),
                    start_line=start_line,
                )
            )
        index += 1
    return fences


def _extract_comment_regions(text: str) -> List[str]:
    regions = []  # type: List[str]
    pos = 0
    while True:
        start = COMMENT_START_RE.search(text, pos)
        if not start:
            break
        end = COMMENT_END_RE.search(text, start.end())
        if not end:
            break
        regions.append(text[start.end() : end.start()].strip())
        pos = end.end()
    return regions


def _extract_heading_fence(text: str) -> Optional[str]:
    lines = text.splitlines()
    index = 0
    while index < len(lines):
        heading = HEADING_RE.match(lines[index])
        if heading:
            title = re.sub(r"\s+", " ", heading.group(2).strip()).lower()
            if title in HEADING_NAMES:
                cursor = index + 1
                while cursor < len(lines) and not lines[cursor].strip():
                    cursor += 1
                if cursor < len(lines):
                    opened = FENCE_OPEN_RE.match(lines[cursor])
                    if opened:
                        marker = opened.group(1)
                        close_re = re.compile(
                            "^"
                            + re.escape(marker[0])
                            + "{"
                            + str(len(marker))
                            + r",}\s*$"
                        )
                        cursor += 1
                        body = []  # type: List[str]
                        while cursor < len(lines):
                            if close_re.match(lines[cursor]):
                                return "\n".join(body).strip("\n")
                            body.append(lines[cursor])
                            cursor += 1
        index += 1
    return None


def _is_spl_fence(fence: Fence) -> bool:
    return fence.language in SPL_LANGUAGES or fence.language in MAIN_LANGUAGES


def _is_main_fence(fence: Fence) -> bool:
    return fence.language in MAIN_LANGUAGES or (
        fence.language in SPL_LANGUAGES and "main" in fence.flags
    )


def _public_metadata(meta: Dict[str, Any]) -> Dict[str, Any]:
    return {
        key: value
        for key, value in meta.items()
        if key not in INTERNAL_META_KEYS
    }


def _optional_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in BOOL_TRUE


def _unquote(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        return value[1:-1]
    return value


def _coerce_yaml_value(value: str) -> Any:
    lowered = value.lower()
    if lowered in BOOL_TRUE:
        return True
    if lowered in BOOL_FALSE:
        return False
    return value
