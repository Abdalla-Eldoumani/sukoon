# Architecture

Owner: Abdalla Eldoumani. Written 2026-10-05. Review again when any of these happen: a third model preset is added, the app is asked to run anywhere other than `127.0.0.1`, or a dependency in the end-of-life table below changes major version.

## Context, goals, non-goals

A local web app that removes music from audio and video files. One person, one machine, one GPU at most. Goals and non-goals are in `docs/requirements.md`; this document covers how it is built and why.

## System sketch

```
 browser (127.0.0.1 only)
   |  HTTP + server-sent events, same origin
   v
 FastAPI app ------------------------------ SQLite (jobs, settings)
   |  validates Host and Origin                 |
   |  streams uploads to disk                   |
   v                                            |
 job runner (one thread) --- ffprobe / ffmpeg subprocesses (argument lists, file and pipe protocols only)
   |                                  ^
   |  multiprocessing queue (spawn)   |  parts checked like an upload, then joined
   v                                  |
 separation worker (one child)     link fetcher (one thread and one child process per link)
   |                                  |
 audio-separator, torch            yt-dlp --- the pasted site and its media servers (https only)
   |
 models folder, SHA-256 checked before load
```

[contributing.md](contributing.md) maps each box to its folder: the app is `sukoon/server/`, the runner and the store are `sukoon/jobs/`, ffmpeg is `sukoon/media/`, the worker is `sukoon/separation/`, and the link fetcher is `sukoon/links/`.

Trust boundaries: the browser is trusted only because it is local, and even so every request is checked for Host and Origin. Uploaded files are untrusted input to ffprobe and ffmpeg. Model files are untrusted until their hash matches. A pasted link is untrusted twice: its address is checked against a fixed list of sites before anything is fetched, and what yt-dlp downloads is checked exactly as an upload is before sukoon's own ffmpeg opens it. The internet is touched only to fetch a model whose hash is already known, and to fetch a link from the site it names when someone pastes it.

## Load model

This is a single-user desktop tool, so the usual sessions-per-second arithmetic does not apply. The load that matters is media throughput on one machine.

- Users: 1. Concurrent separations: 1 (one GPU, and a second job would only slow both).
- Typical input: 3 to 30 minutes. Worst accepted input: 6 hours, 8 GB.
- Decoded working audio is 32-bit float stereo at 44.1 kHz: 21.2 MB per minute, 1.27 GB per hour. A job holds two copies on disk at peak (mixture and voice), so a six-hour file needs about 15 GB of scratch space before its upload and output are counted.
- Throughput measured on 2026-10-05 in a two-core x86 sandbox, 30-second clip, torch 2.14.1 CPU: Fast (MDX-Net Voc FT) took 67 s, 0.45 times real time; Best (Mel-Band RoFormer) took 151 to 199 s, about 0.2 times real time. Model load: 5 s and 5 to 14 s.
- Measured on 2026-10-06 on the RTX 3060 Laptop GPU (6 GB, driver 617.14) with `sukoon bench`: Best 6.7 times real time (median of three 30-second runs). Fast 1.1 times real time, because Fast runs on onnxruntime's CPU build (see the pre-mortem). The target was 10 times; 6.7 is enough for the single-user case, an hour of audio in about 9 minutes.
- Quality measured on 2026-10-06 on 90 seconds of LibriVox speech mixed with an instrumental hip-hop beat at equal loudness: SI-SDR against the clean speech went from 0.3 dB to 18.1 dB with Best and 16.1 dB with Fast. Chunked and whole-file separation of a three-minute mix differ by 0.6 dB. On speech with no music, Best keeps the level (gain 0.998) and Fast lowers it by about 7 dB.

## Capacity and spike plan

The tightest ceiling is GPU memory: 6 GB on the target laptop. The worker processes 60-second chunks, which keeps peak VRAM bounded regardless of file length. CUDA out-of-memory on a chunk retries that chunk once on CPU and marks the job "finished on CPU" so the user knows why it slowed down.

The second ceiling is disk, checked twice. Before an upload streams in, free space must exceed its size plus 1 GB. Once it is on disk and probed, free space must exceed 2.6 GB per hour of audio for scratch, plus an output estimate the size of the upload, plus 1 GB headroom; otherwise the job is refused.

There is no spike to absorb: the queue holds at most 50 waiting jobs and runs them in order. The HTTP capacity test used for networked services does not apply to a server that only ever has one client on loopback; the throughput benchmark above takes its place.

## Data map

| Data | System of record | Derived from it |
| --- | --- | --- |
| Job metadata and state | SQLite `jobs.db` in the data folder, `jobs` table | Live events sent to the browser |
| A link job's address, site, and bytes fetched | `jobs.link`, JSON | The row's "from youtube.com" line and its progress |
| Settings (preset, device, default formats) | `jobs.db`, `settings` table of keys and JSON values | Defaults applied to each new upload |
| Theme | The browser's `localStorage`; `public/theme.js` reads it before the page paints | The `data-theme` on the page |
| Uploaded file | `uploads/<job id>/source.<ext>` | Decoded mixture WAV, original preview |
| A link's downloaded parts | `uploads/<job id>/part0.<ext>`, `part1.<ext>` while fetching; joined into `source.<ext>` and deleted | The source file |
| Decoded mixture | `work/<job id>/` (the whole folder is deleted when the job ends) | Separated voice, waveform peaks |
| Separated voice | `work/<job id>/voice.wav` | Output file, cleaned preview, waveform peaks |
| Output file | `outputs/<job id>/output.<ext>`; the name `<name> (no music).<ext>` is only offered in the download header | |
| Review data | `outputs/<job id>/peaks.json`, `preview-original.webm`, `preview-clean.webm` (Opus) | The review player |
| Models | `models/<file>`, with `<file>.part` while downloading; includes the three settings tables audio-separator reads (`download_checks.json`, `mdx_model_data.json`, `vr_model_data.json`) | |

Invariants and what enforces them:

- At most one separation runs at any time. Enforced by there being exactly one worker process and one runner thread; there is no code path that starts a second.
- A job ID maps to exactly one folder per area, and no path outside the data folder is ever read or written. Enforced by building every path from the data root and the job's UUID, never from user input, and by a single helper that resolves the path and rejects anything not under the root.
- A model is loaded only after its SHA-256 matches the pinned value. Enforced in the one function that hands a model path to the worker.
- A job is in exactly one state. Enforced by a `CHECK` constraint on the state column and by transitions going through one function that validates the from-state.
- An output exists only for a job in state `done`. The output is written to a temporary name and renamed into place as the last step before the state change.

Recovery: if the app dies, nothing is lost but in-flight work. Interrupted jobs restart from the beginning on Retry because the upload is still on disk.

## Dependencies

| Dependency | Fails how | User sees | Handling |
| --- | --- | --- | --- |
| ffmpeg / ffprobe (system install) | Missing, too old, missing an encoder | Setup screen naming the install command | `sukoon doctor` and a startup check; formats needing a missing encoder are hidden |
| GitHub release hosting (models) | Slow, down, rate limited, offline | Model download card with retry | Resumable download with timeout, SHA-256 check, clear offline message; once downloaded, works offline |
| torch CUDA | No GPU, old driver, OOM | Device badge says CPU; OOM note on the job | Auto-detect; per-chunk CPU fallback |
| audio-separator | Import error, model load error | Job fails with the error's message | Pinned version; its settings tables are pinned and hash-checked like the models, so loading needs no network; a crashed worker is replaced |
| Browser codec support | Cannot play the video codec | Waveform-only player with a note | Detect `error` on the video element |
| yt-dlp and the sites it reads (link imports only) | A site changes its pages, refuses signed-out requests, blocks non-browser clients, or is unreachable | The link job fails with a sentence; an out-of-date reader gets the update command | Pinned version; `sukoon doctor` warns when it is 60 days old; nothing updates itself; every failure is mapped to a sentence by `explain()` in `sukoon/links/ytdlp.py` |
| Node.js (YouTube links) | Missing or older than 22 | YouTube links fail as "out of date"; doctor says FAIL with the install command | yt-dlp runs YouTube's JavaScript checks in Node with the bundled `yt-dlp-ejs`, never a downloaded solver |

## Security and privacy threats

- **Another website talks to the local server** (CSRF, DNS rebinding). Host header allowlist and Origin check on every state-changing route; no CORS headers at all.
- **A crafted media file makes ffmpeg read other files or the network.** Probe first and reject playlist and indirection formats; run ffmpeg and ffprobe with `-protocol_whitelist file,pipe`; never pass a user string as an argument.
- **Path traversal through file names.** User file names are kept only as display strings in the database and in the `Content-Disposition` header (RFC 6266 `filename*`). On disk everything is a UUID.
- **A swapped model file runs code when loaded.** Pinned SHA-256 on every model file; torch 2.14 loads with `weights_only=True` by default; the Demucs path, which loads with `weights_only=False`, is not used.
- **Resource exhaustion from a huge or malformed file.** Size, duration, and disk checks before work starts; every ffmpeg call has a timeout scaled to the file's duration, ffprobe and the tool checks have fixed timeouts (60 and 20 seconds), and the separation worker is stopped if a chunk reports no progress for 30 minutes.
- **A pasted link reaches somewhere other than the site it names.** The address must be `https`, with a hostname that is exactly, or ends in a dot plus, one of twelve names; no user part, no port, no raw address, no non-ASCII letters. yt-dlp may only use the extractors of that site's family, so its generic extractor never runs, and every address it is asked to read, including one a post hands on (an X card's t.co link), is checked against the same list before any request, so a post that links another site is refused. Short links (fb.watch, v.redd.it) are followed one redirect at a time, each checked against the same list. yt-dlp reads no config file, uses no cookies or browser profile, loads no plugins (`YTDLP_NO_PLUGINS`), fetches no remote solver, runs no post-processor, and has no ffmpeg of its own (`ffmpeg_location` points nowhere), so it cannot hand a stream to another program; only http, https, HLS and DASH parts are accepted.
- **A link delivers something that is not media.** Each downloaded part goes through the same `inspect()` an upload does (playlist bytes, ffprobe with file and pipe protocols, the demuxer denylist) before sukoon's own ffmpeg joins video and audio, and the joined file goes through the full upload check. The source keeps its extension only if an upload's would be kept, and the size limit holds while the bytes arrive. A link can put nothing on disk that an upload could not.
- **A fetch hangs or crashes.** yt-dlp runs in its own spawned child; Cancel kills it, ten minutes without progress kills it, and it exits if the server dies. Metadata is checked first: live streams, DRM, more than 6 hours, or an estimated 8 GB are refused before any media is downloaded.
- **Agents and model calls reading private data.** Not applicable: the app makes no model API calls.

## Cost

Zero at any scale. There are no usage-billed services. The network cost is a one-time 980 MB of model downloads, plus whatever links the user pastes.

## Compliance

No personal data is collected and nothing is transmitted, so no privacy law is triggered. Users process their own files on their own machine; the README says that users are responsible for having the right to the media they process, including media they fetch by link under each site's terms, and that the models are downloaded from their authors' release pages under their authors' terms.

## Decisions

- Python backend with a browser UI, rather than separation in the browser with WebGPU. See `docs/adr/0001-local-python-backend.md`.
- Keep every voice, including singing. See `docs/adr/0002-keep-all-voices.md`.
- Separation in a dedicated child process. See `docs/adr/0003-separation-worker-process.md`.
- Pin model hashes and download them ourselves. See `docs/adr/0004-pinned-model-hashes.md`.
- Fetch pasted links with a pinned yt-dlp in a child process, from a fixed list of sites. See `docs/adr/0005-link-imports.md`.
- Copy the video stream instead of re-encoding. Two-way door; the re-encode path exists only for containers that cannot hold the codec.
- SQLite from the standard library rather than a server database or JSON files. Two-way door.
- Plain CSS with custom properties and CSS modules, no CSS framework; no animation library, motion uses CSS transitions and the View Transitions API. Two-way doors.
- Themes are blocks of the same custom properties, one per theme, picked before the page paints by a static script (`public/theme.js`), since the content security policy blocks inline scripts. Two-way door.

## Pre-mortem

1. **The GPU path does not work on Windows** because torch was installed from PyPI (CPU only on Windows) instead of the PyTorch CUDA index. This happened: with `cpu` and `cuda` extras, a plain `uv run` re-synced to PyPI's torch and dropped CUDA. Design change: torch and torchvision are ordinary dependencies taken from the CUDA 12.6 index on Windows and Linux (the build also runs without a GPU) and from the CPU index on macOS, so `uv sync` and `uv run` always agree, and `sukoon doctor` prints the device torch actually sees. onnxruntime stays on its CPU build, because the GPU build on PyPI targets CUDA 13; Fast therefore runs on the CPU everywhere.
2. **torch and torchvision come from different indexes** and the MDX model fails to load with `operator torchvision::nms does not exist`. This happened during the 2026-10-05 spike. Design change: both are pinned to the same index in `pyproject.toml`.
3. **Audio drifts against video** after muxing because the audio stream started at a non-zero time or the encoder added priming samples. Design change: the voice is decoded on the source track's own clock (`-copyts` with `aresample` filling from the track's first timestamp), the mux puts it back at that start with `-itsoffset`, and MP4 and MOV outputs get one measured trim for the AAC encoder's priming. Files whose clock starts late, such as MPEG-TS, are rebased so the earliest stream starts at zero. Tests compare the speech in source and output by cross-correlation on their absolute timelines, relative to where the picture moved, across ten container and track combinations plus two late-clock cases, to within 1 ms (1.5 ms for the late-clock cases). One known limit: MP4 to MKV can land about 1 ms off, because Matroska stores whole milliseconds.
4. **Chunk seams are audible.** Design change: 4-second overlaps with a linear crossfade, and a test that compares chunked output with whole-file output on the same clip.
5. **First run feels broken** because the 913 MB model downloads silently. Design change: the model download is a visible step with progress and the option to start with Fast.

## Deferred decisions

| Decision | Revisit when |
| --- | --- |
| Dialogue, music, and effects separation | Users report missing sound effects as the main complaint |
| Running two jobs in parallel on large GPUs | A user with 16 GB or more of VRAM asks for it |
| Packaged installer (no Python or Node needed) | The app is used by people who do not use a terminal |
| Interface translation | Someone asks for a specific language |

## How we know it works

- Automated suite: pipeline tests on the generated fixture corpus with a fake separator, API tests, interface component tests, and real-model tests (opt-in, CPU) with SDR thresholds.
- `sukoon doctor` output on the target machine.
- Live link tests, opt-in with `SUKOON_TEST_NETWORK=1`: one short public video per site family, fetched, cleaned, checked as MP4 or M4A, and deleted. Sites that refuse signed-out requests are expected failures with their reason.
- `sukoon bench --preset best|fast --device auto|cpu` separates a generated 30-second clip three times and prints the median real-time factor. The RTX 3060 numbers are in the load model above.

## End-of-life dates

| Component | Version | End of support |
| --- | --- | --- |
| Python | 3.12 | October 2028 |
| Node.js (build only) | 24 LTS | April 2028 |
| PyTorch | 2.14 | No fixed date; follow releases |
| audio-separator | 0.47.0 | No fixed date; actively released |
| yt-dlp | 2026.8.19 | Releases every few weeks; doctor warns after 60 days |
