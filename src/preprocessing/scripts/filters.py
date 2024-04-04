import math
import typing
import zlib
from pathlib import Path
import re
from typing import Any, Callable
import collections
from urllib.parse import urlparse

import regex
from hojichar import Document
from hojichar.core.filter_interface import Filter
from hojichar.filters.document_filters import (
    AcceptJapanese,
    DiscardAds,
    DiscardRareKuten,
    NgWordsFilterJa,
)

BASE_PATH = Path(__file__).parent


def reformat_data(text_field: str) -> Callable[..., dict[str, Any]]:
    def reformat(example: dict[str, Any]) -> dict[str, Any]:
        text = example[text_field]
        meta = example.get("meta", {})
        meta.update({k: v for k, v in example.items() if k not in {text_field, "meta"}})
        return {"text": text, "meta": meta}

    return reformat


def has_valid_domain() -> Callable[..., bool]:
    dict_path = BASE_PATH.joinpath("dict/ja_valid_domains.txt")
    valid_domains = set(dict_path.read_text().splitlines())

    def judge(example: dict[str, Any]) -> bool:
        if example["meta"]["url"].startswith("https://ja.wikipedia.org/"):
            return False
        domain: typing.Optional[str] = urlparse(example["meta"]["url"]).hostname
        assert domain is not None
        tld = domain.split(".")[-1]
        return tld in valid_domains

    return judge


def has_valid_extension() -> Callable[..., bool]:
    dict_path = BASE_PATH.joinpath("dict/code_valid_extensions.txt")
    valid_extensions = set(dict_path.read_text().splitlines())

    def judge(example: dict[str, Any]) -> bool:
        # https://github.com/togethercomputer/RedPajama-Data/blob/main/data_prep/github/github_run_filter.py
        return example["meta"]["ext"] in valid_extensions

    return judge


def has_valid_max_line_length(
    allowed_max_line_length: int = 1_000,
) -> Callable[..., bool]:
    def judge(example: dict[str, Any]) -> bool:
        # https://github.com/togethercomputer/RedPajama-Data/blob/main/data_prep/github/github_run_filter.py
        return example["meta"]["max_line_length"] <= allowed_max_line_length

    return judge


def has_valid_avg_line_length(
    allowed_avg_line_length: int = 100,
) -> Callable[..., bool]:
    def judge(example: dict[str, Any]) -> bool:
        # https://github.com/togethercomputer/RedPajama-Data/blob/main/data_prep/github/github_run_filter.py
        return example["meta"]["avg_line_length"] <= allowed_avg_line_length

    return judge


def has_valid_alphanum_fraction(
    allowed_alphanum_fraction: float = 0.25,
) -> Callable[..., bool]:
    def judge(example: dict[str, Any]) -> bool:
        # https://github.com/togethercomputer/RedPajama-Data/blob/main/data_prep/github/github_run_filter.py
        return example["meta"]["alphanum_fraction"] >= allowed_alphanum_fraction

    return judge


def has_good_compression_ratio(
    min_score: float = 0.3, max_score: float = 0.7, length_factor: float = 0.0
) -> Callable[..., bool]:
    """Checks if data compression (deflate) yields a desired size of data stream.

    NOTE(odashi, 2023-09-03):
    Ths judgment is based on an assumption that a "natual" sentence has an entropy
    within a certain range, and both "too simple" (low entropy) and "too complex" (high
    entropy) sentences don't reflect human's usual writing.
    This function calculates the data compression ratio (calculated by the Deflate
    algorithm) of the original stream, and compares if the resulting ratio is in-between
    the specified range.
    This criterion is somewhat sensitive against the length of the original stream (e.g.
    if the input is long, the resulting compression ratio tends to be small).
    This function also has a mechanism to consider the original length (adjusted by the
    `length_factor` parameter).

    Args:
        min_score: The lower bound of the compression ratio.
        max_score: The upper bound of the compression ratio.
        length_factor: Penalty factor of log(original_byte_length), usually set to
            something larger than 0. Using 0 falls back to a simple compression ratio.

    Returns:
        Judgment function, bound with `min` and `max`.

    Example:
        >>> judge = has_good_compression_ratio(0.1, 1.0, 0.0)
        >>> judge({"text": "LbdJA66Ufy4Pr6ffQEIo0DL60OL7kQl6y6ohAhqYKf3laCruuR"})
        False  # 1.16
        >>> judge({"text": "a" * 200})
        False  # 0.06
        >>> judge({"text": "This is a usual sentence. This sentence should pass this judgment."})
        True  # 0.92
    """

    def judge(example: dict[str, Any]) -> bool:
        encoded = example["text"].encode("utf-8")
        compressed = zlib.compress(encoded, level=9)
        encoded_length = len(encoded)
        compressed_length = len(compressed)
        ratio = compressed_length / encoded_length
        length_penalty = (
            length_factor * math.log(encoded_length) if length_factor else 0.0
        )
        score = ratio + length_penalty
        return min_score <= score <= max_score

    return judge


def is_japanese() -> Callable[..., bool]:
    accept_japanese_filter = AcceptJapanese()

    def judge(example: dict[str, Any]) -> bool:
        doc = accept_japanese_filter.apply(Document(example["text"]))
        return not doc.is_rejected

    return judge


def is_not_empty() -> Callable[..., bool]:
    def judge(example: dict[str, Any]) -> bool:
        return example["text"].strip() != ""

    return judge


def has_good_average_sentence_length(
    max_average_sentence_length: int = 250,
) -> Callable[..., bool]:
    content_filter = DiscardRareKuten(
        max_average_sentence_length=max_average_sentence_length
    )

    def judge(example: dict[str, Any]) -> bool:
        doc = content_filter.apply(Document(example["text"]))
        return not doc.is_rejected

    return judge


def is_not_adult_content(max_allowed_num: int = 3) -> Callable[..., bool]:
    dict_path = BASE_PATH.joinpath("dict/ja_adult_keywords.txt")

    # Monkey patch for hojichar
    def apply(self, doc):
        if len(self.keyword_pat.findall(doc.text)) > max_allowed_num:
            doc.is_rejected = True
        return doc

    content_filter = NgWordsFilterJa(dict_path, ignore_confused=True)
    content_filter.apply = apply.__get__(content_filter, NgWordsFilterJa)

    def judge(example: dict[str, Any]) -> bool:
        doc = content_filter.apply(Document(example["text"]))
        return not doc.is_rejected

    return judge


def is_not_discrimination_content(max_allowed_num: int = 3) -> Callable[..., bool]:
    dict_path = BASE_PATH.joinpath("dict/ja_discrimination_keywords.txt")

    # Monkey patch for hojichar
    def apply(self, doc):
        if len(self.keyword_pat.findall(doc.text)) > max_allowed_num:
            doc.is_rejected = True
        return doc

    content_filter = NgWordsFilterJa(dict_path, ignore_confused=True)
    content_filter.apply = apply.__get__(content_filter, NgWordsFilterJa)

    def judge(example: dict[str, Any]) -> bool:
        doc = content_filter.apply(Document(example["text"]))
        return not doc.is_rejected

    return judge


def is_not_violence_content(max_allowed_num: int = 3) -> Callable[..., bool]:
    dict_path = BASE_PATH.joinpath("dict/ja_violence_keywords.txt")

    # Monkey patch for hojichar
    def apply(self, doc):
        if len(self.keyword_pat.findall(doc.text)) > max_allowed_num:
            doc.is_rejected = True
        return doc

    content_filter = NgWordsFilterJa(dict_path, ignore_confused=True)
    content_filter.apply = apply.__get__(content_filter, NgWordsFilterJa)

    def judge(example: dict[str, Any]) -> bool:
        doc = content_filter.apply(Document(example["text"]))
        return not doc.is_rejected

    return judge


def is_not_ad_content(max_allowed_num: int = 10) -> Callable[..., bool]:
    content_filter = DiscardAds(max_allowed_num=max_allowed_num)

    def judge(example: dict[str, Any]) -> bool:
        doc = content_filter.apply(Document(example["text"]))
        return not doc.is_rejected

    return judge


def extract_japanese_text() -> Callable[..., dict[str, Any]]:
    def extract(example: dict[str, Any]) -> dict[str, Any]:
        ja_pat = regex.compile(r"[\p{Script=Hiragana}\p{Script=Katakana}ー]+")
        script_pat = regex.compile(
            r"[\u0000-\u007F\u0020-\u002F\u003A-\u0040\u005B-\u0060\u007B-\u007E]{100,}"
        )
        url_pat = regex.compile(r"https?://[\w/:%#\$&\?\(\)~\.=\+\-]+")

        def regex_filter(sentence: str, pat) -> str:
            valid: str = ""
            index: int = 0
            for m in pat.finditer(sentence):
                valid += sentence[index : m.start()]
                index = m.end()
            valid += sentence[index:]
            return valid

        valid: str = ""
        for sentence in example["text"].split("\n"):
            if ja_pat.search(sentence):
                sentence = regex_filter(sentence, url_pat)
                sentence = regex_filter(sentence, script_pat)
                valid += sentence
        example["text"] = valid
        return example

    return extract


def remove_wikipedia_footnote() -> Callable[..., dict[str, Any]]:
    def remove(example: dict[str, Any]) -> dict[str, Any]:
        footnote_sections: list[str] = [
            "脚注",
            "関連項目",
            "日本国内の関連項目",
            "出典",
            "出典・脚注",
            "参照",
            "外部リンク",
            "参考文献",
            "その他関連事項",
            "Footnotes",
            "See also",
            "Further reading",
            "Bibliography",
            "References",
            "Notes",
            "Citations",
            "Sources",
            "External links",
        ]
        footnote_pat = regex.compile(rf"\n({'|'.join(footnote_sections)})\s*\n")
        m = footnote_pat.search(example["text"])
        if m:
            example["text"] = example["text"][: m.start()]
        return example

    return remove


def remove_empty_parenthesis() -> Callable[..., dict[str, Any]]:
    def remove(example: dict[str, Any]) -> dict[str, Any]:
        # Japanese
        example["text"] = regex.sub(r"（[\s,，、;；]*", "（", example["text"])
        example["text"] = regex.sub(r"[\s,，、;；]*）", "）", example["text"])
        example["text"] = regex.sub(r"（\s*）", "", example["text"])
        # English
        example["text"] = regex.sub(r"\([\s,;]*", "(", example["text"])
        example["text"] = regex.sub(r"[\s,;]*\)", ")", example["text"])
        example["text"] = regex.sub(r"\s?\(\s*\)", "", example["text"])
        return example

    return remove


# 行の重複比率をチェックする関数
def has_below_duplicate_line_ratio(
    max_duplicate_ratio: float = 0.30,
) -> Callable[..., bool]:
    def judge(example: dict[str, Any]) -> bool:
        lines = re.sub(r"\n+", "\n", example["text"]).strip().split("\n")
        duplicate_count = sum(
            (count) for line, count in collections.Counter(lines).items() if count > 1
        )
        duplicate_ratio = duplicate_count / len(lines) if lines else 0
        return duplicate_ratio <= max_duplicate_ratio

    return judge


# 段落の重複比率をチェックする関数
def has_below_duplicate_paragraph_ratio(
    max_duplicate_ratio: float = 0.30,
) -> Callable[..., bool]:
    def judge(example: dict[str, Any]) -> bool:
        paragraphs = example["text"].split("\n\n")
        duplicate_count = sum(
            (count)
            for paragraph, count in collections.Counter(paragraphs).items()
            if count > 1
        )
        duplicate_ratio = duplicate_count / len(paragraphs) if paragraphs else 0
        return duplicate_ratio <= max_duplicate_ratio

    return judge


# 行における重複する文字数の比率をチェックする関数
def has_below_duplicate_line_char_ratio(
    max_duplicate_char_ratio: float = 0.20,
) -> Callable[..., bool]:
    def judge(example: dict[str, Any]) -> bool:
        lines = re.sub(r"\n+", "\n", example["text"]).strip().split("\n")
        all_chars = example["text"].replace("\n", "")
        duplicate_chars_count = sum(
            (count) * len(line)
            for line, count in collections.Counter(lines).items()
            if count > 1
        )
        duplicate_char_ratio = (
            duplicate_chars_count / len(all_chars) if all_chars else 0
        )
        return duplicate_char_ratio <= max_duplicate_char_ratio

    return judge


# 段落における重複する文字数の比率をチェックする関数
def has_below_duplicate_paragraph_char_ratio(
    max_duplicate_char_ratio: float = 0.20,
) -> Callable[..., bool]:
    def judge(example: dict[str, Any]) -> bool:
        paragraphs = example["text"].split("\n\n")
        all_chars = example["text"].replace("\n", "")
        duplicate_chars_count = sum(
            (count) * len(paragraph.replace("\n", ""))
            for paragraph, count in collections.Counter(paragraphs).items()
            if count > 1
        )
        duplicate_char_ratio = (
            duplicate_chars_count / len(all_chars) if all_chars else 0
        )
        return duplicate_char_ratio <= max_duplicate_char_ratio

    return judge


# 最頻出の n-gram の出現回数 / 全 n-gram の出現回数
def has_below_max_ngram_ratio(n: int, max_ratio: float) -> Callable[..., bool]:
    def judge(example: dict[str, Any]) -> bool:
        text = example["text"].replace("\n", " ").replace("。", "")
        ngrams = [text[i : i + n] for i in range(len(text) - n + 1)]
        ngram_counts = collections.Counter(ngrams)
        max_ngram_count = max(ngram_counts.values()) if ngram_counts else 0
        total_ngram_count = sum(ngram_counts.values())
        ratio = max_ngram_count / total_ngram_count if total_ngram_count > 0 else 0
        return ratio <= max_ratio

    return judge


# 2 回以上出現する n-gram の総出現回数 / 全n-gram の総出現回数
def has_below_repeated_ngram_ratio(
    n: int, max_ratio: float, min_repeats: int = 2
) -> Callable[..., bool]:
    def judge(example: dict[str, Any]) -> bool:
        text = example["text"].replace("\n", " ").replace("。", "")
        ngrams = [text[i : i + n] for i in range(len(text) - n + 1)]
        ngram_counts = collections.Counter(ngrams)
        repeated_ngram_count = sum(
            count for count in ngram_counts.values() if count >= min_repeats
        )
        total_ngram_count = sum(ngram_counts.values())
        ratio = repeated_ngram_count / total_ngram_count if total_ngram_count > 0 else 0
        return ratio <= max_ratio

    return judge


# 文章中の文の文字数の平均の割合によるフィルタリングのためのhojiChar
class DiscardRareKutenBySwallow(Filter):
    def __init__(
        self,
        min_average_sentence_length: int = 20,
        max_average_sentence_length: int = 90,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)

        self.max_average_sentence_length = max_average_sentence_length
        self.min_average_sentence_length = min_average_sentence_length
        self.kuten_pat = re.compile(r"。")

    def apply(self, doc: Document) -> Document:
        kuten_lst = self.kuten_pat.findall(doc.text)
        min_kuten_num = len(doc.text) / self.max_average_sentence_length
        max_kuten_num = len(doc.text) / self.min_average_sentence_length
        if len(kuten_lst) < min_kuten_num or max_kuten_num < len(kuten_lst):
            doc.is_rejected = True
        return doc


# 文章中の文の文字数の平均の割合によるフィルタリング
def has_good_average_sentence_length_by_swallow(
    min_average_sentence_length: int = 20,
    max_average_sentence_length: int = 90,
) -> Callable[..., bool]:
    content_filter = DiscardRareKutenBySwallow(
        min_average_sentence_length=min_average_sentence_length,
        max_average_sentence_length=max_average_sentence_length,
    )

    def judge(example: dict[str, Any]) -> bool:
        doc = content_filter.apply(Document(example["text"]))
        return not doc.is_rejected

    return judge


# 最も長い文の文字数が200文字以上でないかをチェックする関数
def has_sentence_with_min_length(min_length: int = 200) -> Callable[..., bool]:
    def judge(example: dict[str, Any]) -> bool:
        sentences = re.split(r"。", example["text"].replace("\n", ""))
        for sentence in sentences:
            if len(sentence) >= min_length:
                return False
        return True

    return judge


# 最小文字数が400文字以上であるかをチェックする関数
def has_documents_with_min_length(min_length: int = 400) -> Callable[..., bool]:
    def judge(example: dict[str, Any]) -> bool:
        return len(example["text"]) >= min_length

    return judge
