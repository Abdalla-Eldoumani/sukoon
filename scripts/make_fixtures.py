"""Generates the test corpus into tests/fixtures/generated (or the folder given).

Usage: python scripts/make_fixtures.py [out_dir]
"""

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf

SR = 44100
DEFAULT_OUT = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "generated"

TEXT = (
    "The river ran quietly past the old mill, and the miller's daughter sat on the stone wall "
    "counting the boats as they drifted by. Each one carried something different: apples from "
    "the northern farms, bolts of grey cloth, crates of glass wrapped in straw. She wrote them "
    "all down in a small notebook with a blue cover, because her father had told her that a "
    "careful record is worth more than a good memory. In the evening the light turned orange "
    "over the water and the last boat passed with its lantern swinging. "
)


def ffmpeg(*args: str) -> None:
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *args], check=True)


def normalise(x: np.ndarray, peak: float = 0.5) -> np.ndarray:
    m = float(np.max(np.abs(x)))
    return x * (peak / m) if m > 0 else x


def fit(x: np.ndarray, seconds: float) -> np.ndarray:
    n = round(seconds * SR)
    if len(x) >= n:
        return x[:n]
    reps = int(np.ceil(n / len(x)))
    return np.concatenate([x] * reps)[:n]


def speech(seconds: float, tmp: Path) -> np.ndarray:
    """Mono speech at 44.1 kHz from espeak-ng at 140 words per minute; a tone pattern without it."""
    if shutil.which("espeak-ng") is None:
        t = np.arange(round(seconds * SR)) / SR
        envelope = (np.sin(2 * np.pi * 3 * t) > 0).astype(np.float64)
        return normalise(np.sin(2 * np.pi * 220 * t) * envelope)
    raw = tmp / "espeak.wav"
    up = tmp / "espeak44.wav"
    subprocess.run(["espeak-ng", "-s", "140", "-w", str(raw), TEXT * 3], check=True)
    ffmpeg("-i", str(raw), "-ar", str(SR), "-ac", "1", "-c:a", "pcm_f32le", str(up))
    data, _ = sf.read(up, dtype="float64")
    return normalise(fit(data, seconds))


def music(seconds: float, seed: int = 7) -> np.ndarray:
    """Stereo bed of triad chords, a kick on every beat, and a hat on every half beat."""
    rng = np.random.default_rng(seed)
    n = round(seconds * SR)
    t = np.arange(n) / SR
    roots = [220.0, 174.61, 196.0, 261.63]
    chords = np.zeros(n)
    for i, start in enumerate(range(0, n, 2 * SR)):
        end = min(n, start + 2 * SR)
        root = roots[i % len(roots)]
        seg = t[start:end]
        for ratio in (1.0, 1.25, 1.5):
            chords[start:end] += np.sin(2 * np.pi * root * ratio * seg)
    beat = int(0.5 * SR)
    kick = np.zeros(n)
    kt = np.arange(int(0.15 * SR)) / SR
    kick_shape = np.sin(2 * np.pi * (60 + 90 * np.exp(-kt * 30)) * kt) * np.exp(-kt * 20)
    hat = np.zeros(n)
    hat_shape = rng.standard_normal(int(0.04 * SR)) * np.exp(-np.arange(int(0.04 * SR)) / 300)
    hat_shape = np.diff(hat_shape, prepend=0.0)
    for start in range(0, n, beat):
        k = kick_shape[: n - start]
        kick[start : start + len(k)] += k
    for start in range(0, n, beat // 2):
        h = hat_shape[: n - start]
        hat[start : start + len(h)] += h
    mono = normalise(chords) + normalise(kick) * 0.9 + normalise(hat) * 0.3
    stereo = np.stack([mono, np.roll(mono, 40) * 0.9], axis=1)
    return normalise(stereo)


def write(path: Path, data: np.ndarray, sr: int = SR, subtype: str = "FLOAT") -> Path:
    sf.write(path, data, sr, subtype=subtype)
    return path


def stereo(x: np.ndarray) -> np.ndarray:
    return np.stack([x, x], axis=1) if x.ndim == 1 else x


def build(out: Path) -> dict[str, Path]:
    out.mkdir(parents=True, exist_ok=True)
    made: dict[str, Path] = {}
    with tempfile.TemporaryDirectory() as tmp_name:
        tmp = Path(tmp_name)
        sp30 = stereo(speech(30, tmp))
        mu30 = music(30)
        made["speech-clean-30s.wav"] = write(out / "speech-clean-30s.wav", sp30)
        made["music-clean-30s.wav"] = write(out / "music-clean-30s.wav", mu30)
        made["speech-over-music-30s.wav"] = write(out / "speech-over-music-30s.wav", sp30 + mu30)
        made["music-only-20s.wav"] = write(out / "music-only-20s.wav", music(20, seed=11))
        made["speech-only-20s.wav"] = write(out / "speech-only-20s.wav", sp30[: 20 * SR])
        mix10 = out / ".mix10.wav"
        write(mix10, (sp30 + mu30)[: 10 * SR])
        made["short-2s.wav"] = write(out / "short-2s.wav", (sp30 + mu30)[: 2 * SR])
        made["mono-22k.wav"] = out / "mono-22k.wav"
        ffmpeg(
            "-i",
            str(mix10),
            "-t",
            "5",
            "-ac",
            "1",
            "-ar",
            "22050",
            "-c:a",
            "pcm_s16le",
            str(made["mono-22k.wav"]),
        )
        made["hires-96k.flac"] = out / "hires-96k.flac"
        ffmpeg(
            "-i",
            str(mix10),
            "-t",
            "5",
            "-ar",
            "96000",
            "-c:a",
            "flac",
            "-sample_fmt",
            "s32",
            "-bits_per_raw_sample",
            "24",
            str(made["hires-96k.flac"]),
        )

        cover = tmp / "cover.png"
        ffmpeg("-f", "lavfi", "-i", "color=c=0x2f4f4f:s=300x300:d=1", "-frames:v", "1", str(cover))
        made["song-with-cover.mp3"] = out / "song-with-cover.mp3"
        ffmpeg(
            "-i",
            str(mix10),
            "-i",
            str(cover),
            "-map",
            "0:a",
            "-map",
            "1:v",
            "-c:a",
            "libmp3lame",
            "-q:a",
            "2",
            "-c:v",
            "png",
            "-disposition:v",
            "attached_pic",
            "-id3v2_version",
            "3",
            "-metadata",
            "title=Test song",
            "-metadata",
            "artist=sukoon fixtures",
            str(made["song-with-cover.mp3"]),
        )

        video = ["-f", "lavfi", "-i", "testsrc2=s=320x240:r=25:d=10"]
        h264 = ["-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p"]

        made["surround-5.1.mp4"] = out / "surround-5.1.mp4"
        ffmpeg(
            *video,
            "-i",
            str(mix10),
            "-filter_complex",
            "[1:a]pan=5.1|FL=c0|FR=c1|FC=0.5*c0+0.5*c1|LFE=0.1*c0|BL=c0|BR=c1[a]",
            "-map",
            "0:v",
            "-map",
            "[a]",
            *h264,
            "-c:a",
            "aac",
            "-b:a",
            "256k",
            str(made["surround-5.1.mp4"]),
        )

        commentary = tmp / "commentary.wav"
        write(commentary, sp30[10 * SR : 20 * SR] * 0.8)
        made["two-tracks.mkv"] = out / "two-tracks.mkv"
        ffmpeg(
            *video,
            "-i",
            str(mix10),
            "-i",
            str(commentary),
            "-map",
            "0:v",
            "-map",
            "1:a",
            "-map",
            "2:a",
            *h264,
            "-c:a",
            "libopus",
            "-b:a",
            "128k",
            "-metadata:s:a:0",
            "language=eng",
            "-metadata:s:a:0",
            "title=Main",
            "-metadata:s:a:1",
            "language=ara",
            "-metadata:s:a:1",
            "title=Commentary",
            "-disposition:a:0",
            "default",
            "-disposition:a:1",
            "0",
            str(made["two-tracks.mkv"]),
        )

        made["offset-0.5s.mp4"] = out / "offset-0.5s.mp4"
        ffmpeg(
            *video,
            "-itsoffset",
            "0.5",
            "-i",
            str(mix10),
            "-map",
            "0:v",
            "-map",
            "1:a",
            *h264,
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-t",
            "10",
            str(made["offset-0.5s.mp4"]),
        )

        subs = tmp / "subs.ass"
        subs.write_text(ASS, encoding="utf-8")
        made["subs-ass.mkv"] = out / "subs-ass.mkv"
        ffmpeg(
            *video,
            "-i",
            str(mix10),
            "-i",
            str(subs),
            "-map",
            "0:v",
            "-map",
            "1:a",
            "-map",
            "2:s",
            *h264,
            "-c:a",
            "libopus",
            "-c:s",
            "copy",
            "-metadata",
            "title=Subtitled",
            str(made["subs-ass.mkv"]),
        )
        chapters = tmp / "chapters.txt"
        chapters.write_text(CHAPTERS, encoding="utf-8")
        with_chapters = tmp / "subs-chapters.mkv"
        ffmpeg(
            "-i",
            str(made["subs-ass.mkv"]),
            "-i",
            str(chapters),
            "-map",
            "0",
            "-map_metadata",
            "0",
            "-map_chapters",
            "1",
            "-c",
            "copy",
            str(with_chapters),
        )
        shutil.move(with_chapters, made["subs-ass.mkv"])

        vfr = tmp / "vfr.mp4"
        ffmpeg(
            "-f",
            "lavfi",
            "-i",
            "testsrc2=s=320x240:r=30:d=10",
            "-i",
            str(mix10),
            "-vf",
            "select='lt(mod(n\\,30)\\,20)+lt(n\\,10)'",
            "-fps_mode",
            "vfr",
            "-map",
            "0:v",
            "-map",
            "1:a",
            *h264,
            "-c:a",
            "aac",
            str(vfr),
        )
        # Rotation is set on a stream copy, since filtering would bake it into the pixels.
        made["vfr-rotated.mp4"] = out / "vfr-rotated.mp4"
        ffmpeg(
            "-display_rotation", "90", "-i", str(vfr), "-c", "copy", str(made["vfr-rotated.mp4"])
        )

        made["video-no-audio.mp4"] = out / "video-no-audio.mp4"
        ffmpeg(*video, *h264, str(made["video-no-audio.mp4"]))

        made["vp9-opus.webm"] = out / "vp9-opus.webm"
        ffmpeg(
            "-f",
            "lavfi",
            "-i",
            "testsrc2=s=320x240:r=25:d=5",
            "-i",
            str(mix10),
            "-t",
            "5",
            "-c:v",
            "libvpx-vp9",
            "-b:v",
            "200k",
            "-deadline",
            "realtime",
            "-cpu-used",
            "8",
            "-c:a",
            "libopus",
            str(made["vp9-opus.webm"]),
        )

        # Still picture for 7 s, then noise: most bytes sit late, so half the bytes holds
        # well over half of the timeline and the decode stops early but usefully.
        full = tmp / "full.mp4"
        ffmpeg(
            "-f",
            "lavfi",
            "-i",
            "color=c=gray:s=320x240:r=25:d=7",
            "-f",
            "lavfi",
            "-i",
            "nullsrc=s=320x240:r=25:d=3,geq=random(1)*255:128:128",
            "-i",
            str(mix10),
            "-filter_complex",
            "[0:v][1:v]concat=n=2:v=1[v]",
            "-map",
            "[v]",
            "-map",
            "2:a",
            *h264,
            "-c:a",
            "aac",
            "-movflags",
            "+faststart",
            str(full),
        )
        data = full.read_bytes()
        made["truncated.mp4"] = out / "truncated.mp4"
        made["truncated.mp4"].write_bytes(data[: len(data) // 2])
        mix10.unlink()

    made["empty.mp4"] = out / "empty.mp4"
    made["empty.mp4"].write_bytes(b"")
    made["text-renamed.mp4"] = out / "text-renamed.mp4"
    made["text-renamed.mp4"].write_text("This is a text file, not a video.\n" * 20)
    made["random-bytes.bin"] = out / "random-bytes.bin"
    made["random-bytes.bin"].write_bytes(np.random.default_rng(3).bytes(64 * 1024))
    made["playlist-local.m3u8"] = out / "playlist-local.m3u8"
    made["playlist-local.m3u8"].write_text(playlist(str(made["speech-only-20s.wav"])))
    made["playlist-remote.m3u8"] = out / "playlist-remote.m3u8"
    made["playlist-remote.m3u8"].write_text(playlist("http://127.0.0.1:1/segment.ts"))
    return made


def playlist(segment: str) -> str:
    return (
        "#EXTM3U\n#EXT-X-VERSION:3\n#EXT-X-TARGETDURATION:20\n#EXT-X-MEDIA-SEQUENCE:0\n"
        f"#EXTINF:20.0,\n{segment}\n#EXT-X-ENDLIST\n"
    )


def make_silence_70min(out: Path) -> Path:
    """70 minutes of silence with a quiet 440 Hz tone every tenth minute, for the slow test."""
    path = out / "silence-70min.flac"
    if not path.exists():
        out.mkdir(parents=True, exist_ok=True)
        ffmpeg(
            "-f",
            "lavfi",
            "-i",
            "sine=f=440:r=44100:d=4200",
            "-af",
            "volume='if(lt(mod(t,600),5),0.3,0)':eval=frame",
            "-ac",
            "2",
            "-c:a",
            "flac",
            str(path),
        )
    return path


ASS = """[Script Info]
ScriptType: v4.00+
PlayResX: 320
PlayResY: 240

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, \
Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, \
Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,16,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,1,0,\
2,10,10,10,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:00.50,0:00:04.00,Default,,0,0,0,,The river ran quietly
Dialogue: 0,0:00:05.00,0:00:09.00,Default,,0,0,0,,past the old mill
"""

CHAPTERS = """;FFMETADATA1
title=Subtitled
[CHAPTER]
TIMEBASE=1/1000
START=0
END=5000
title=Opening
[CHAPTER]
TIMEBASE=1/1000
START=5000
END=10000
title=Ending
"""

if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUT
    for name, path in sorted(build(target).items()):
        print(f"{path.stat().st_size:>10}  {name}")
