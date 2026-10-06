import os
import subprocess
from collections.abc import Callable
from pathlib import Path

from sukoon import ffmpeg, tools
from sukoon.compat import AUDIO_ENCODER, MUXER, REENCODE, Plan
from sukoon.encode import MAX_RATE
from sukoon.probe import Probe


def first_time(path: Path, selector: str, entry: str) -> float | None:
    """Time of the first decoded audio frame (entry "frame") or first packet ("packet")."""
    exe = tools.ffprobe_path()
    if exe is None:
        return None
    show = "-show_frames" if entry == "frame" else "-show_packets"
    out = subprocess.run(
        [
            exe,
            "-v",
            "error",
            "-protocol_whitelist",
            "file,pipe",
            "-select_streams",
            selector,
            show,
            "-read_intervals",
            "%+2",
            "-show_entries",
            f"{entry}=pts_time",
            "-of",
            "csv=p=0",
            str(path),
        ],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    times = []
    for line in out.stdout.split():
        try:
            times.append(float(line.strip(",")))
        except ValueError:
            continue
    # Packets come in decode order, so the earliest time is not always the first one read.
    return min(times) if times else None


def _args(
    voice_wav: Path,
    source: Path,
    probe: Probe,
    track: int,
    plan: Plan,
    offset: float,
    trim: float,
    partial: Path,
) -> list[str]:
    chosen = probe.audio[track]
    args = ["-copyts", "-protocol_whitelist", "file,pipe", "-i", str(source)]
    if trim > 0:
        args += ["-ss", f"{trim:.6f}"]
    args += [
        "-protocol_whitelist",
        "file,pipe",
        "-itsoffset",
        f"{offset:.6f}",
        "-i",
        str(voice_wav),
    ]
    for stream in probe.video:
        args += ["-map", f"0:{stream.index}"]
    if plan.reencode:
        _, encoder, options = REENCODE[plan.container]
        args += ["-c:v", encoder, *options]
    else:
        args += ["-c:v", "copy"]

    encoder, bitrate = AUDIO_ENCODER[plan.container]
    for out_index, (stream, step) in enumerate(zip(probe.audio, plan.audio, strict=True)):
        args += ["-map", "1:a:0" if stream is chosen else f"0:{stream.index}"]
        if step.action == "copy":
            args += [f"-c:a:{out_index}", "copy"]
            continue
        rate = 48000 if encoder == "libopus" else min(stream.sample_rate or MAX_RATE, MAX_RATE)
        args += [
            f"-c:a:{out_index}",
            encoder,
            f"-b:a:{out_index}",
            bitrate,
            f"-ar:a:{out_index}",
            str(rate),
            f"-ac:a:{out_index}",
            str(min(stream.channels or 2, 2)),
        ]
        if stream is chosen:
            # The new track takes the place of the old one, so it inherits its labels.
            for key, value in (("language", stream.language), ("title", stream.title)):
                if value:
                    args += [f"-metadata:s:a:{out_index}", f"{key}={value}"]
            args += [f"-disposition:a:{out_index}", "default" if stream.default else "0"]

    for out_index, step in enumerate(plan.subtitles):
        args += [
            "-map",
            f"0:{step.index}",
            f"-c:s:{out_index}",
            "copy" if step.action == "copy" else str(step.codec),
        ]
    if plan.attachments:
        args += ["-map", "0:t?", "-c:t", "copy"]
    args += [
        "-map_metadata",
        "0",
        "-map_chapters",
        "0",
        "-f",
        MUXER[plan.container],
        "-y",
        str(partial),
    ]
    return args


def mux_video(
    voice_wav: Path,
    source: Path,
    probe: Probe,
    track: int,
    plan: Plan,
    out_path: Path,
    on_progress: Callable[[float], None],
    cancelled: Callable[[], bool],
) -> None:
    """Copies the picture and swaps in the voice track, in sync, keeping everything else it can.

    The voice WAV starts at the source track's start time, and both are muxed on the source's
    own clock, so the speech lands where it was. AAC's priming can still show up in front of
    it when the track starts late, which moves the track's start time. That is measured once
    and, if present, cut from the front of the voice and muxed again; a cut under -copyts
    keeps every remaining sample at its original time.
    """
    partial = out_path.with_name(f".{out_path.name}.part")
    start = probe.audio[track].start_time
    timeout = None if plan.reencode is None else 600 + probe.duration * 20
    try:
        ffmpeg.run(
            _args(voice_wav, source, probe, track, plan, start, 0.0, partial),
            probe.duration,
            on_progress,
            cancelled,
            timeout=timeout,
        )
        # Only AAC shows its priming as an earlier start. Matroska reports an Opus track's first
        # frame after taking off its codec delay, so that time is not the speech's time.
        # ceiling: a re-encoded picture is not muxed twice, since that would encode it again;
        # its audio may start up to one priming length early. Revisit if that is noticed.
        aac = AUDIO_ENCODER[plan.container][0] == "aac"
        priming = (
            _visible_priming(source, partial, track, start) if aac and not plan.reencode else None
        )
        if priming is not None:
            ffmpeg.run(
                _args(voice_wav, source, probe, track, plan, start, priming, partial),
                probe.duration,
                lambda _f: None,
                cancelled,
            )
        os.replace(partial, out_path)
    finally:
        partial.unlink(missing_ok=True)


def _visible_priming(source: Path, output: Path, track: int, start: float) -> float | None:
    """How far before its start the new track begins, when that is worth fixing."""
    landed = first_time(output, f"a:{track}", "packet")
    source_video = first_time(source, "v:0", "packet")
    output_video = first_time(output, "v:0", "packet")
    if landed is None or source_video is None or output_video is None:
        return None
    # Muxers may move a whole file's clock; the picture shows by how much.
    early = start + (output_video - source_video) - landed
    return early if 0.001 < early < 0.2 else None
