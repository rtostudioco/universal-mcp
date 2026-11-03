"""Módulo ``ai`` — análisis de texto 100% local (sin APIs externas).

Implementa NLP ligero con librería estándar: tokenización, resumen
extractivo por frecuencia, análisis de sentimiento por léxico ES/EN,
extracción de keywords y entidades simples (emails/urls/teléfonos).
"""

from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter
from typing import Any

from universal_mcp.core.base import BaseModule
from universal_mcp.core.context import ModuleContext
from universal_mcp.core.exceptions import ToolExecutionError
from universal_mcp.core.utils import to_json
from universal_mcp.modules.ai.nlp_data import NEGATIVE_WORDS, POSITIVE_WORDS, STOPWORDS

_WORD_RE = re.compile(r"[a-záéíóúüñ0-9]+", re.IGNORECASE)
_SENTENCE_RE = re.compile(r"(?<=[.!?…])\s+")

_EXTRACTORS: dict[str, str] = {
    "emails": r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",
    "urls": r"https?://[^\s)\]>\"']+",
    "phones": r"\+?\d[\d\s().-]{7,}\d",
    "numbers": r"-?\d+(?:[.,]\d+)?",
}


# ----------------------------------------------------------------------
# Implementaciones puras
# ----------------------------------------------------------------------
def tokenize(text: str) -> list[str]:
    return [token.lower() for token in _WORD_RE.findall(text)]


def text_stats_impl(text: str) -> dict[str, Any]:
    words = _WORD_RE.findall(text)
    sentences = [s for s in _SENTENCE_RE.split(text.strip()) if s.strip()]
    paragraphs = [p for p in re.split(r"\n\s*\n", text.strip()) if p.strip()]
    word_count = len(words)
    return {
        "chars": len(text),
        "chars_no_spaces": len(text.replace(" ", "").replace("\n", "")),
        "words": word_count,
        "unique_words": len({w.lower() for w in words}),
        "sentences": len(sentences),
        "paragraphs": len(paragraphs),
        "avg_word_length": round(sum(len(w) for w in words) / word_count, 2) if word_count else 0.0,
        "reading_time_min": math.ceil(word_count / 200) if word_count else 0,
    }


def summarize_impl(text: str, max_sentences: int = 3) -> dict[str, Any]:
    sentences = [s.strip() for s in _SENTENCE_RE.split(text.strip()) if s.strip()]
    limit = max(1, min(max_sentences, 10))
    if not sentences:
        raise ToolExecutionError("No hay frases para resumir.")
    if len(sentences) <= limit:
        return {
            "summary": " ".join(sentences),
            "summary_sentences": len(sentences),
            "original_sentences": len(sentences),
            "note": "El texto ya era corto; se devuelve completo.",
        }
    freq = Counter(w for w in tokenize(text) if w not in STOPWORDS)
    scored: list[tuple[int, float]] = []
    for index, sentence in enumerate(sentences):
        tokens = [w for w in tokenize(sentence) if w not in STOPWORDS]
        score = (sum(freq.get(w, 0) for w in tokens) / math.sqrt(len(tokens))) if tokens else 0.0
        scored.append((index, score))
    keep = {index for index, _ in sorted(scored, key=lambda pair: pair[1], reverse=True)[:limit]}
    summary = " ".join(sentences[index] for index in sorted(keep))
    return {
        "summary": summary,
        "summary_sentences": len(keep),
        "original_sentences": len(sentences),
    }


def sentiment_impl(text: str) -> dict[str, Any]:
    tokens = [w for w in tokenize(text) if w.isalpha()]
    positives = [w for w in tokens if w in POSITIVE_WORDS]
    negatives = [w for w in tokens if w in NEGATIVE_WORDS]
    total = len(positives) + len(negatives)
    score = (len(positives) - len(negatives)) / total if total else 0.0
    label = "positive" if score > 0.15 else "negative" if score < -0.15 else "neutral"
    return {
        "score": round(score, 3),
        "label": label,
        "positive_matches": positives,
        "negative_matches": negatives,
        "note": "Análisis léxico local (ES/EN); score ∈ [-1, 1].",
    }


def keywords_impl(text: str, top: int = 10) -> dict[str, Any]:
    tokens = [w for w in tokenize(text) if w not in STOPWORDS and not w.isdigit() and len(w) > 2]
    limit = max(1, min(top, 50))
    counter = Counter(tokens)
    return {
        "keywords": [{"word": word, "count": count} for word, count in counter.most_common(limit)],
        "unique_tokens": len(counter),
    }


def extract_impl(text: str, kind: str = "emails") -> dict[str, Any]:
    if kind not in _EXTRACTORS:
        raise ToolExecutionError(
            f"Tipo desconocido: {kind!r}. Usa uno de: {', '.join(_EXTRACTORS)}."
        )
    matches = re.findall(_EXTRACTORS[kind], text)
    return {"kind": kind, "matches": matches[:100], "match_count": len(matches)}


def slugify_impl(text: str) -> dict[str, str]:
    normalized = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "-", normalized.lower()).strip("-")
    return {"slug": slug or "n-a"}


# ----------------------------------------------------------------------
# Registro de tools
# ----------------------------------------------------------------------
class AIModule(BaseModule):
    name = "ai"
    description = "Análisis de texto local: resumen, sentimiento, keywords y extracción."

    def register(self, ctx: ModuleContext) -> None:
        @ctx.tool(
            name="text_stats",
            description="Text metrics: chars, words, unique words, sentences, paragraphs, reading time.",
        )
        def text_stats(text: str) -> str:
            return to_json(text_stats_impl(text))

        @ctx.tool(
            name="summarize",
            description=(
                "Extractive summary: picks the most relevant sentences (word-frequency "
                "scoring, ES/EN stopwords) keeping original order. Max 10 sentences."
            ),
        )
        def summarize(text: str, max_sentences: int = 3) -> str:
            try:
                return to_json(summarize_impl(text, max_sentences))
            except ToolExecutionError as exc:
                return to_json({"error": str(exc), "type": type(exc).__name__})

        @ctx.tool(
            name="sentiment",
            description="Lexicon-based sentiment for Spanish/English text. Returns score in [-1,1] and label.",
        )
        def sentiment(text: str) -> str:
            return to_json(sentiment_impl(text))

        @ctx.tool(
            name="keywords",
            description="Top keywords by frequency (stopwords ES/EN removed).",
        )
        def keywords(text: str, top: int = 10) -> str:
            return to_json(keywords_impl(text, top))

        @ctx.tool(
            name="extract",
            description="Extract entities by regex: kind ∈ {emails, urls, phones, numbers}.",
        )
        def extract(text: str, kind: str = "emails") -> str:
            try:
                return to_json(extract_impl(text, kind))
            except ToolExecutionError as exc:
                return to_json({"error": str(exc), "type": type(exc).__name__})

        @ctx.tool(
            name="slugify",
            description="Convert text to a URL-friendly slug (ASCII, hyphen-separated).",
        )
        def slugify(text: str) -> str:
            return to_json(slugify_impl(text))
