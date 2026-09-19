"""Where a claim was read from, and the one normalization its offsets are measured in.

`Location` is a tagged union. Today it has a single variant, `CharSpan`, which holds
character offsets into the normalized paper text. It is a union from the start so a
`PageBox` variant (PDF page + bounding box) can join it later without a schema
migration; PDF is out of scope here, so no such variant exists yet.

**The contract, stated once so it cannot be misread:** a `CharSpan`'s offsets are
**character** offsets — Python string indices — into the text returned by
`normalize_text`. They are *not* byte offsets, and *not* offsets into the raw input.
This matters beyond tidiness: C6's paper hash covers the same normalized text these
offsets index. If the two ever disagreed, a published verdict would point at different
content than the one it was derived from.

This module emits no verdicts. It records where a number was found, nothing more.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import ClassVar
import unicodedata

__all__ = ["CharSpan", "Location", "normalize_text"]


def normalize_text(raw: str) -> str:
    """Return `raw` in the single normal form every offset is measured against.

    It does exactly two things, in this order:

    1. CRLF (`\\r\\n`) becomes LF (`\\n`), so a file checked out on Windows and the
       same file on macOS yield *identical* offsets.
    2. Unicode NFC, so a composed character and its decomposed twin (`é` vs `e` +
       combining acute) count as one character rather than one or two.

    Nothing else. No dehyphenation, no whitespace collapsing, no case folding, no
    stripping. Each of those would shift offsets away from the text the paper hash
    covers, and none is needed for the text/Markdown input this aspect handles.

    A lone `\\r` is deliberately left alone: the stated rule is CRLF→LF, and silently
    rewriting bare carriage returns would be a third behaviour.

    The function is idempotent — `normalize_text(normalize_text(s)) ==
    normalize_text(s)` — so re-applying it to already-normalized text is safe, but the
    pipeline still applies it exactly once, at intake, and indexes only the result.
    """
    return unicodedata.normalize("NFC", raw.replace("\r\n", "\n"))


class Location(ABC):
    """Base of the location union. Variants are discriminated by `kind`.

    Abstract on purpose: a bare `Location` would be a reference with no way to resolve
    it back to source text.

    **`__slots__ = ()` is load-bearing — do not delete it as boilerplate.** A base class
    that omits `__slots__` carries a `__dict__` descriptor, and every subclass inherits
    it. That silently defeats the subclass's own `slots=True`: the variant declares its
    slots, looks sealed, and still accepts `object.__setattr__(span, "confidence", 0.9)`
    into the inherited dict. Removing this line would re-open every variant of the union
    at once — including ones that did everything right — which is exactly the guardrail
    `CLAUDE.md` #1 keeps off these records. Both declarations are required: the empty
    slots here, and `slots=True` on each variant.
    """

    __slots__ = ()

    kind: ClassVar[str]

    @abstractmethod
    def __init__(self) -> None:  # pragma: no cover - never called
        ...

    def __init_subclass__(cls, **kwargs: object) -> None:
        # Enforced rather than documented: an untagged variant would be
        # indistinguishable from a `CharSpan` once aspect 3 serializes the union.
        super().__init_subclass__(**kwargs)
        if not isinstance(getattr(cls, "kind", None), str):
            raise TypeError(
                f"{cls.__name__} must set a `kind` tag to join the Location union"
            )


@dataclass(frozen=True, slots=True)
class CharSpan(Location):
    """A half-open `[start, end)` character span of the normalized text.

    `normalize_text(raw)[span.start:span.end]` is the exact source text the claim was
    read from. Offsets are character offsets into the *normalized* text (see the module
    docstring); reading them as byte offsets or as offsets into the raw input gives the
    wrong span.

    Impossible spans are rejected at construction rather than carried: a negative
    offset would make Python's slicing wrap around and silently return a *different*
    span, and `start > end` would silently return the empty string. Both would put a
    plausible-looking but wrong quotation into a claim record, which is worse than a
    loud failure at the point of the mistake. A zero-width span (`start == end`) is
    legal — it addresses a position rather than a quotation.
    """

    kind: ClassVar[str] = "char_span"

    start: int
    end: int

    def __post_init__(self) -> None:
        for name in ("start", "end"):
            value = getattr(self, name)
            # `bool` is an `int` subclass; True as an offset is a bug, not an index.
            if not isinstance(value, int) or isinstance(value, bool):
                raise TypeError(
                    f"CharSpan.{name} must be an int character offset, "
                    f"got {type(value).__name__}: {value!r}"
                )
        if self.start < 0 or self.end < 0:
            raise ValueError(
                f"CharSpan offsets must be non-negative, got "
                f"start={self.start}, end={self.end}"
            )
        if self.start > self.end:
            raise ValueError(
                f"CharSpan start must not exceed end, got "
                f"start={self.start}, end={self.end}"
            )
