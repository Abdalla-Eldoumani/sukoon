# Behaviour when things go wrong

What sukoon does in every case that isn't the happy path, and the test that proves it. How often each case comes up is in brackets. The test files generate their input files with `scripts/make_fixtures.py`; the names below are those files.

## Input

| Case | What happens | Proved by |
| --- | --- | --- |
| **Not a media file** (common): a PDF, a renamed text file, an empty file | The browser filters by type, but the server decides: a zero-byte upload is refused before probing, and anything ffprobe can't read or that has no audio stream is refused with "This file isn't audio or video sukoon can read." The upload is deleted. | API tests with `empty.mp4`, `text-renamed.mp4`, `random-bytes.bin` |
| **Video with no sound** (common) | "This video has no sound track, so there is nothing to clean." | API test with `video-no-audio.mp4` |
| **Cover art on an MP3** (common): ffprobe reports the picture as a video stream | A video stream marked `attached_pic`, or with a single frame, doesn't make a file a video. The cover is carried into outputs that hold one (MP3, M4A, FLAC). | `song-with-cover.mp3`: classified as audio, output keeps the picture |
| **Playlist or indirection file** (rare, and the only way to make ffmpeg read other files) | Probing runs with `-protocol_whitelist file,pipe`, and the format is checked against a denylist (`hls`, `concat`, `sdp`, `rtp`, `rtsp`, `tee`, `image2`, `image2pipe`, `dash`, `imf`, and any name ending in `_pipe`). A DASH manifest is also recognised by its content in the first megabyte and refused before ffprobe runs, because that demuxer fetches the addresses in a manifest while it is being probed: "This is a playlist, not a media file." | Security tests: an `.m3u8` or an `.mpd` pointing at a local file and at `http://127.0.0.1:1/` is refused and makes no request |
| **Several audio tracks** (rare): languages, commentary | The job waits in "Choose track" showing each track's language, title, and channels, with the default track preselected. The CLI takes `--track N`. Only the chosen track is replaced; the others are copied unchanged. | `two-tracks.mkv`: output has both tracks, only the chosen one changed |
| **Surround sound** (rare) | Downmixed to stereo with ffmpeg's default matrix before separation, and the result says "Surround was mixed down to stereo." | `surround-5.1.mp4` |
| **Mono, odd sample rates, high bit depth** (common) | Decoded to 44.1 kHz stereo float for the model. Output keeps the source's channel count (mono stays mono) and sample rate up to 48 kHz; WAV and FLAC are 24-bit. | `mono-22k.wav`, `hires-96k.flac`: rate, channels, and duration match |
| **Very short file** (rare): shorter than the model's window | Padded with silence to 10 seconds, then trimmed back to the exact sample count. | Real-model test on `short-2s.wav` |
| **Very long file** (rare): a four-hour lecture | Accepted up to 6 hours. Processed in 60-second chunks with 4-second overlaps, so memory doesn't grow with length. The time estimate appears after the first chunk. Disk space is checked before the upload is accepted. | A 70-minute file through the worker stays under 400 MB of memory; with a stand-in engine, chunked and whole-file output match to within 1e-6, and with the real model the chunked result's SI-SDR is within 1 dB of the whole file's |
| **Damaged file** (rare): a truncated download | No readable duration: refused at probe. Decoding stops early: the job carries on with what decoded and says "The source file is damaged after mm:ss; the output stops there." Less than half the probed duration decoded: the job fails. | `truncated.mp4` |
| **Phone video and odd codecs** (common): variable frame rate, HEVC, rotation, ProRes | The picture is copied, so frame timing and rotation survive. If the browser can't preview it, see Browser below. | Video packets byte-identical, rotation tag kept |

## Links

Every failure below fails the link job with the sentence shown, on its row, and keeps Retry unless retrying can't help. The sentences are in `sukoon/links/messages.py`; `explain()` in `sukoon/links/ytdlp.py` maps yt-dlp's errors to them. Where a sentence names a site, the site changes with the link.

| Case | What happens | Proved by |
| --- | --- | --- |
| **Refused address** (common): an unlisted site, a look-alike host (`youtube.com.evil.example`, a Cyrillic letter for a Latin one), a user part, a port, a raw address, `http` | Refused before a job exists and before any request, under the link field: "sukoon takes links from YouTube, X, Facebook, Reddit, and SoundCloud. It also tries Instagram, TikTok, and Vimeo, which often turn it away. For anything else, download the file and drop it here." | Unit tests on `site()` with each look-alike; API test that a refused link makes no job |
| **Playlist or channel** (common) | Read without expanding its entries: "This link is a playlist or a channel. Paste the link of one video." A single video taken from a playlist (`watch?v=...&list=...`) is fetched alone. | Unit test on `refusal()`; checked live on a YouTube playlist |
| **Private or deleted** (common) | "This video is private or was deleted, so it can't be fetched." | `explain()` with yt-dlp's wording; API test through the stand-in downloader |
| **Age-restricted** (rare) | "This video is age-restricted, and sukoon never signs in, so it can't be fetched." | `explain()` |
| **Signed-in people only** (common on some sites): Vimeo today, or a 401 or 403 | "Vimeo only shares this video with signed-in people, and sukoon never signs in. Save it another way and drop the file here." | `explain()`; the live Vimeo test is an expected failure with this reason |
| **Sent without sound** (common on Instagram today) | The file fails the sound check: "Instagram sent this video without its sound, so there is nothing to clean. Some sites hold the sound back from people who aren't signed in." | API test with a silent file; the live Instagram test is an expected failure with this reason |
| **Region-locked** (rare) | "This video isn't available in your region." yt-dlp's geo error is recognised by type as well as wording. | `explain()` |
| **Live stream** (rare): live, upcoming, or just ended | Refused from the metadata before anything downloads: "This is a live stream. Paste the link again once it has ended." | `refusal()` for each live status |
| **Too long or too big** (rare): over 6 hours, or an estimated 8 GB from the sizes the site gives or bitrate times duration | Refused from the metadata: "This video is longer than 6 hours, which is sukoon's limit." or "This video is bigger than 8 GB, which is sukoon's limit." A site that gives no size is held to the limit while the bytes arrive. | `refusal()`; a stand-in downloader that reports too many bytes is stopped |
| **DRM, or a stream sukoon doesn't fetch** (rare): copy protection, or a protocol yt-dlp would hand to another program such as RTMP | "This video is protected against copying (DRM), so it can't be fetched." or "This video is only offered as a kind of stream sukoon doesn't fetch." | `refusal()` |
| **Network drop** (rare) | yt-dlp retries first, then "The connection dropped while fetching. Check your connection, then retry." The partial parts are deleted; Retry starts over. | `explain()` with yt-dlp's DNS failure |
| **Out-of-date reader** (common over months): the site changed its pages | "yt-dlp couldn't read this Vimeo page. Its reader may be out of date, or Vimeo turned the request away. To update it, run: uv lock --upgrade-package yt-dlp --upgrade-package yt-dlp-ejs && uv sync". `sukoon doctor` warns once yt-dlp is 60 days old. Nothing updates itself. | `explain()` with "please report this issue"; doctor tests on the age line |
| **Turned away** (common on TikTok today): the site answers with something other than its page | "TikTok turned the request away, as it does with many requests that don't come from a browser. Save the video another way and drop the file here." | `explain()` with "Unexpected response from webpage request"; the live TikTok test is an expected failure |
| **A post that links elsewhere** (rare): a Reddit or X post whose video lives on another site | Every address yt-dlp is asked to read, including one a post hands on (an X card's t.co link), is checked against the list first, and only the pasted site's extractors run: "This post points to a video on another site. Open it there and paste that link." | `explain()`; offline tests that t.co, an unlisted site, and `http` are refused before any request |
| **A fetch that hangs or crashes** (rare) | The download runs in its own child process. Ten minutes without a word: "The download made no progress for 10 minutes, so it was stopped." A crash: "The download stopped unexpectedly." Cancel kills it at once. If the app stops during a fetch, the job comes back interrupted, quietly, and Retry fetches again. | Stand-in downloaders that stall, crash, and run across a restart or a shutdown |

## Separation

| Case | What happens | Proved by |
| --- | --- | --- |
| **No music** (common): a plain voice recording | The removed lane is nearly flat. Removed energy under 1% of the input: "There was almost no music in this file." | Real-model test on speech only |
| **No voice** (common): an instrumental | Kept voice under -50 dBFS RMS: "No voices were found; the output is nearly silent." The output is still made. | Real-model test on music only |
| **Singing, humming, vocal percussion** (common) | Kept, by design ([ADR 2](adr/0002-keep-all-voices.md)). The empty page and the README say voices stay. | Documented; no test |
| **GPU runs out of memory** (rare) | The chunk is retried on the processor after emptying the CUDA cache; later chunks try the GPU again. "Part of this ran on the CPU because the GPU ran out of memory." | Worker test with an engine that raises `torch.cuda.OutOfMemoryError` once |
| **No GPU, or torch without CUDA** (common on first setup) | The top bar shows the device actually in use. `sukoon doctor` says when an NVIDIA GPU is present but torch can't use it, and how to fix it. | Doctor test with CUDA mocked |
| **The worker crashes** (rare): a native crash or a driver reset | The runner sees the child exit, fails the job with "The separation engine stopped unexpectedly", and starts a fresh worker. Retry works. | An engine that calls `os._exit(1)` mid-job: that job fails, the next succeeds |

## Models

| Case | What happens | Proved by |
| --- | --- | --- |
| **No model yet** (every new install) | The model card appears above the queue: download Best, or start with Fast. The job waits in "Waiting for model". Progress shows bytes and speed. | API test with a fake download source |
| **Offline, or the host is down** (rare) | Downloads go to a `.part` file that stays across a restart and resumes with an HTTP Range request. "Couldn't download the model. Check your connection, then retry." with Retry. After the download, sukoon never needs the network. | A local server that drops the connection halfway, then resumes |
| **Model file corrupted or replaced** (very rare) | SHA-256 is checked after every download and before the first load in a process. A mismatch deletes the file: "The model file didn't match its expected checksum and was removed." | A fixture model with one byte flipped |

## Output

| Case | What happens | Proved by |
| --- | --- | --- |
| **Container can't hold the picture's codec** (rare): VP9 into MOV, ProRes into WebM | Decided before the job starts. The job asks to confirm: "The picture will be re-encoded to H.264 for MP4 (about as long as the video's duration on this machine)". WebM re-encodes to VP9 only when the source isn't VP8, VP9, or AV1. | Unit tests on the compatibility table; a pipeline test that forces a re-encode |
| **Subtitles that won't copy** (rare): image or ASS subtitles into MP4 | Text subtitles convert to `mov_text` for MP4 and MOV; others are dropped and the result says "Subtitles were left out because MP4 can't hold them; choose MKV to keep them." | `subs-ass.mkv` to MP4 and to MKV |
| **Audio starts later than the picture** (common in edited exports), or AAC adds priming samples | The voice is decoded on the source track's clock and put back at its start time; MP4 and MOV get one measured trim for AAC priming; files whose clock starts late are rebased to zero. | `offset-0.5s.mp4`, ten container and track pairs, and two files whose clock starts late: speech lines up with the source to within 1 ms (1.5 ms for the late ones) |
| **Awkward names** (common): Arabic, emoji, `<>:"/\|?*`, trailing dots, 200 characters | Names are never used on disk. The download name has reserved characters replaced by `-`, trailing dots and spaces removed, and is cut to 150 characters before ` (no music).ext`, sent as RFC 6266 `filename*=UTF-8''...`. | Unit tests on each kind of name |
| **Lossy to the same lossy format** (common): MP3 in, MP3 out | Encoded high enough not to hear the second pass: MP3 VBR V0, AAC 256 kbps, Opus 160 kbps, Vorbis q6. FLAC and WAV are there for no loss at all. | The format matrix test checks the encoder settings |

## Queue and lifecycle

| Case | What happens | Proved by |
| --- | --- | --- |
| **Upload interrupted** (rare on one computer) | Uploads stream to a `.part` file that's deleted when the request ends early. A sweep at startup removes any upload or output `.part` older than an hour; a model's `.part` is kept, because the download resumes from it. | API test that aborts an upload |
| **Tab closed while working** (common) | Work is on the server and carries on. Reopening shows where it is. | Disconnect and reconnect the event stream mid-job |
| **App stopped while working** (rare): Ctrl+C, restart, power cut | At the next start every running job becomes `interrupted` and its scratch folder is deleted. Retry starts it over. | A database seeded with a running job |
| **Cancel while separating** (common) | The worker checks between chunks. A chunk that doesn't answer within 20 seconds gets the worker stopped and replaced. Cancel while encoding kills ffmpeg. The job ends `canceled` with its scratch deleted. | A slow engine cancels within one chunk; a hung one is stopped within 25 s |
| **Disk fills up mid-job** (rare) | Any `ENOSPC` fails the job with "The disk is full." and deletes its scratch and partial output. Outputs are written under a temporary name and renamed when complete, so a full disk never leaves a broken file that looks finished. | A writer patched to raise `OSError(ENOSPC)` |
| **Two tabs** (common) | All state is on the server and both tabs get the same events. Actions are safe to repeat (cancelling a cancelled job does nothing). | Two event-stream clients |
| **Port in use** (common) | If 8417 answers `/api/health` as sukoon, the browser opens on it and the new process exits. Otherwise the next free port up to 8427 is used and printed. | A dummy listener on 8417 |

## Setup

| Case | What happens | Proved by |
| --- | --- | --- |
| **No ffmpeg** (every new install) | The interface shows one screen with the install command for the platform and Check again. `sukoon doctor` prints the same. | `PATH` emptied |
| **ffmpeg missing an encoder** (rare) | Encoders are listed at startup with `ffmpeg -encoders`; formats that need a missing one are disabled with a tooltip naming it. | A patched encoder list |
| **Windows paths** (common): spaces, non-ASCII letters, long paths | Every subprocess gets an argument list, never a shell; paths are built with `pathlib`; `doctor` prints the data folder. | `SUKOON_HOME` set to a folder with Arabic letters and spaces |

## Browser

| Case | What happens | Proved by |
| --- | --- | --- |
| **A codec the browser can't play** (common for phone video): HEVC in Firefox, ProRes anywhere | The video element's `error` switches the review to the strip with "Your browser can't preview this video; the downloaded file is fine." | Component test firing `error` |
| **Compare drifts** (common over minutes) | Both audio previews come from one decoded timeline. Every 250 ms, a follower more than 40 ms off is moved, aiming ahead by what its last correction took to land (up to 250 ms; a bigger jump is the user seeking). With video, the video is the clock. | Fake media elements running at different rates |
| **Keyboard and screen reader** | Choose files is the alternative to dropping; every row and control is in tab order; each row's name, state, and progress is its accessible description; progress is announced politely at most every 10%; holding C also works as the Original switch. | Keyboard pass; axe-core on the main states |
| **Narrow window** (rare for a desktop tool): 375 px | Rows stack into two lines, the settings sheet goes full width, the hold-C hint is hidden, and nothing scrolls sideways. | Screenshots at 375, 768, 1440 |
| **Storage blocked** (rare): the theme can't be saved | Every storage access is wrapped; the theme falls back to System. | Tests with `localStorage` throwing |
