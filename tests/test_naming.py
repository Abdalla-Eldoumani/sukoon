import pytest

from sukoon.naming import content_disposition, download_name


@pytest.mark.parametrize(
    ("original", "ext", "expected"),
    [
        ("lecture.mp3", "mp3", "lecture (no music).mp3"),
        ("حلقة ١.mp4", "mp4", "حلقة ١ (no music).mp4"),
        ("party 🎉.wav", "flac", "party 🎉 (no music).flac"),
        ('a<b>c:d"e/f\\g|h?i*j.mkv', "mkv", "a-b-c-d-e-f-g-h-i-j (no music).mkv"),
        ("trailing... .mp3", "mp3", "trailing (no music).mp3"),
        ("noext", "wav", "noext (no music).wav"),
        ("....mp3", "mp3", "sukoon (no music).mp3"),
        ("tab\there.mp3", "mp3", "tab-here (no music).mp3"),
    ],
)
def test_download_name(original, ext, expected):
    assert download_name(original, ext) == expected


def test_long_names_are_cut_to_150_characters_before_the_suffix():
    name = download_name("x" * 200 + ".mp3", "mp3")
    assert name == "x" * 150 + " (no music).mp3"


def test_content_disposition_carries_utf8_and_an_ascii_fallback():
    header = content_disposition("حلقة (no music).mp4")
    assert header.startswith("attachment; ")
    assert "filename*=UTF-8''%D8%AD%D9%84%D9%82%D8%A9%20%28no%20music%29.mp4" in header
    assert 'filename="---- (no music).mp4"' in header


def test_content_disposition_escapes_quotes_in_the_fallback():
    assert 'filename="a-b (no music).mp3"' in content_disposition('a"b (no music).mp3')
