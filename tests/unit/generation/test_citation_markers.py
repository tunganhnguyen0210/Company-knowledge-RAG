import re

from generation.service import normalize_citation_markers

# The exact regex evaluation/metrics.py uses to decide whether a sentence is cited.
_METRIC_MARKER = re.compile(r"\[C\d+\]")


def test_grouped_marker_is_split_into_one_bracket_per_source() -> None:
    assert normalize_citation_markers("Hồ sơ gồm hai giấy tờ [C3, C4].") == (
        "Hồ sơ gồm hai giấy tờ [C3][C4]."
    )


def test_grouped_marker_variants_are_all_normalized() -> None:
    assert normalize_citation_markers("a [C1,C3]. b [C1; C2]. c [C4 , C10].") == (
        "a [C1][C3]. b [C1][C2]. c [C4][C10]."
    )


def test_already_canonical_markers_are_left_untouched() -> None:
    answer = "Không đúng [C3]. Hồ sơ nộp tại cấp huyện [C3][C4]."

    assert normalize_citation_markers(answer) == answer


def test_normalized_answer_is_countable_by_the_metric_regex() -> None:
    # The real failure from run1/ADV-014: the sentence carried a citation but the
    # metric could not see it, scoring the answer 0.333 instead of 1.0.
    answer = "Hồ sơ bao gồm thông báo và hợp đồng mua bán [C3, C4]."

    assert not _METRIC_MARKER.search(answer)
    assert _METRIC_MARKER.search(normalize_citation_markers(answer))


def test_plain_prose_with_brackets_is_not_mangled() -> None:
    answer = "Khoản 2 Điều 17 [C1] quy định rõ (xem thêm [1, 2] trong phụ lục)."

    assert normalize_citation_markers(answer) == answer
