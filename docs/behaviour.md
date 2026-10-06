# Behaviour when things go wrong

Each case says what happens, how often it is likely, and how the app handles it. Every case with a test names it; the generated fixture corpus (see the test fixtures script) produces the input files.

## Input

### Not a media file
**Scenario:** a PDF, a text file renamed `.mp4`, or an empty file is dropped.
**Frequency:** common. **Impact:** wasted wait, confusing failure.
**Handling:** the browser filters by `accept`, but the server decides. ffprobe runs on the upload; if it finds no audio stream or fails to parse, the job is rejected with "This file isn't audio or video sukoon can read." Zero-byte uploads are rejected before probing. The upload is deleted.
**Verification:** API tests with `empty.mp4`, `text-renamed.mp4`, `random-bytes.bin`.

### Video with no audio track
**Scenario:** a screen recording without sound.
**Frequency:** common. **Impact:** nothing to do.
**Handling:** rejected at probe with "This video has no sound track, so there is nothing to clean."
**Verification:** API test with `video-no-audio.mp4`.

### Cover art makes an MP3 look like a video
**Scenario:** an MP3 or M4A carries an embedded picture, which ffprobe reports as a video stream.
**Frequency:** common. **Impact:** wrong player, wrong output formats offered.
**Handling:** a video stream with the `attached_pic` disposition, or with a single frame, does not make a file a video. The cover is carried into audio outputs that support it (MP3, M4A, FLAC).
**Verification:** pipeline test with `song-with-cover.mp3`: classified as audio, output still has the picture.

### Playlist or indirection file
**Scenario:** an `.m3u8`, `.txt` concat list, `.sdp`, or similar file that would make ffmpeg open other paths or URLs.
**Frequency:** rare but real, and the only route to reading other files on disk. **Impact:** security.
**Handling:** probing runs with `-protocol_whitelist file,pipe`, and the probed `format_name` is checked against a denylist (`hls`, `concat`, `sdp`, `rtp`, `rtsp`, `tee`, `image2`, `image2pipe` and any format whose name ends in `_pipe`) before anything else runs. Rejected with "This is a playlist, not a media file."
**Verification:** security test with an `.m3u8` pointing at a local file and at `http://127.0.0.1:1/`: rejected, and no request is made.

### Several audio tracks
**Scenario:** a film with a main track and a commentary track, or several languages.
**Frequency:** rare but real. **Impact:** wrong language cleaned.
**Handling:** the job pauses in "Choose track" showing each track's language tag, title, and channel layout; the default-disposition track is preselected; one click continues. The CLI takes `--track N` and otherwise uses the default. Only the chosen track is replaced; the others are copied into the output unchanged.
**Verification:** pipeline test with `two-tracks.mkv`: output has two tracks, only track 2 changed.

### Surround sound
**Scenario:** 5.1 or 7.1 audio.
**Frequency:** rare. **Impact:** models expect stereo.
**Handling:** downmixed to stereo with ffmpeg's default matrix before separation; output is stereo; the finished job notes "Surround was mixed down to stereo."
**Verification:** pipeline test with `surround-5.1.mp4`.

### Mono, odd sample rates, high bit depth
**Scenario:** a 22.05 kHz mono voice memo, a 96 kHz 24-bit FLAC.
**Frequency:** common. **Impact:** wrong pitch or speed if mishandled.
**Handling:** decoded to 44.1 kHz stereo float for the model. Output goes back to the source channel count (mono stays mono) and the source sample rate capped at 48 kHz. WAV and FLAC outputs are 24-bit.
**Verification:** pipeline tests with `mono-22k.wav` and `hires-96k.flac`: output rate, channels, and duration match.

### Very short file
**Scenario:** a two-second clip, shorter than the model's internal chunk.
**Frequency:** rare but real. **Impact:** model error.
**Handling:** padded with silence to 10 seconds before separation and trimmed back to the exact original sample count afterwards.
**Verification:** real-model test on `short-2s.wav`: succeeds, length exact.

### Very long file
**Scenario:** a four-hour lecture.
**Frequency:** rare but real. **Impact:** memory, disk, and patience.
**Handling:** accepted up to 6 hours (configurable). Processed in 60-second chunks with 4-second overlaps, so memory use does not grow with length. The ETA appears after the first chunk. Disk need is checked before upload is accepted.
**Verification:** pipeline test with the fake separator on a 70-minute silent-plus-tone file asserts chunk count and constant peak memory in the worker (under 1.5 GB); chunked versus whole-file comparison on a 3-minute clip stays under -60 dB difference outside the crossfades and under -40 dB inside them.

### Damaged file
**Scenario:** a truncated MP4 from a failed download, or a file with decode errors in the middle.
**Frequency:** rare but real. **Impact:** crash or silent truncation.
**Handling:** if ffprobe cannot read a duration, rejected at probe. If decoding stops early, the job continues with what decoded and the result notes "The source file is damaged after mm:ss; the output stops there." A decode producing less than 50% of the probed duration fails the job instead.
**Verification:** pipeline test with `truncated.mp4` (half the bytes of a valid file).

### Variable frame rate and odd video codecs
**Scenario:** phone recordings (VFR, HEVC, rotation metadata), ProRes from an editor.
**Frequency:** common. **Impact:** broken sync or rotated output if re-encoded.
**Handling:** the video stream is copied, so frame timing and rotation side data survive. The browser preview may not play HEVC or ProRes; that is handled by the player fallback below.
**Verification:** pipeline test with a VFR fixture: video packets byte-identical, rotation tag preserved.

## Links

Every failure below fails the link job with the sentence shown, inline on its row, and keeps Retry unless retrying cannot help. The sentences live in `src/sukoon/links.py`.

### Refused site
**Scenario:** a link to a site that is not on the list, a look-alike host (`youtube.com.evil.example`, a Cyrillic letter in place of a Latin one), a user part (`https://youtube.com@evil.example`), a port, a raw address, or `http`.
**Frequency:** common. **Impact:** a request to somewhere the user did not mean.
**Handling:** refused before a job exists and before any network request: "sukoon takes links from YouTube, X, Instagram, TikTok, Facebook, Reddit, Vimeo, and SoundCloud. For anything else, download the file and drop it here." The sentence appears under the link field.
**Verification:** unit tests on `site()` with each look-alike; API test that a refused link makes no job.

### Playlist or channel
**Scenario:** a playlist, a channel, or a profile page.
**Frequency:** common. **Impact:** hundreds of downloads from one paste.
**Handling:** the metadata is read without expanding the entries and the job fails with "This link is a playlist or a channel. Paste the link of one video." A single video taken from a playlist (`watch?v=...&list=...`) is fetched alone.
**Verification:** unit test on `refusal()`; checked live on a YouTube playlist (refused in 2 s).

### Private or deleted video
**Scenario:** the video was made private or removed.
**Frequency:** common. **Impact:** nothing to fetch.
**Handling:** "This video is private or was deleted, so it can't be fetched."
**Verification:** unit test on `explain()` with yt-dlp's wording; API test through the stand-in downloader.

### Age-restricted
**Scenario:** the site asks the viewer to sign in to confirm their age.
**Frequency:** rare but real. **Impact:** nothing to fetch without an account.
**Handling:** "This video is age-restricted, and sukoon never signs in, so it can't be fetched."
**Verification:** unit test on `explain()`.

### Only for signed-in people
**Scenario:** the site serves the video only to signed-in users (Vimeo's web client does this today), or answers 401 or 403.
**Frequency:** common on some sites. **Impact:** nothing to fetch.
**Handling:** "Vimeo only shares this video with signed-in people, and sukoon never signs in. Save it another way and drop the file here." The site's name changes with the link.
**Verification:** unit test on `explain()`; the live Vimeo test is an expected failure with this reason.

### Sent without sound
**Scenario:** the site sends signed-out viewers the picture without its sound track (Instagram does this today).
**Frequency:** common on that site. **Impact:** nothing to clean.
**Handling:** the downloaded file fails the sound check, and the job says "Instagram sent this video without its sound, so there is nothing to clean. Some sites hold the sound back from people who aren't signed in."
**Verification:** API test with a silent fixture; the live Instagram test is an expected failure with this reason.

### Region-locked
**Scenario:** the uploader made the video unavailable in the user's country.
**Frequency:** rare. **Impact:** nothing to fetch.
**Handling:** "This video isn't available in your region." yt-dlp's geo error is recognised by type as well as by wording.
**Verification:** unit tests on `explain()`.

### Live stream
**Scenario:** a stream that is live, about to start, or just ended and still being processed.
**Frequency:** rare but real. **Impact:** a download with no end.
**Handling:** refused from the metadata, before anything downloads: "This is a live stream. Paste the link again once it has ended."
**Verification:** unit tests on `refusal()` for each live status.

### Too long or too big
**Scenario:** more than 6 hours, or an estimated size over 8 GB (from the file sizes the site gives, or the bitrate times the duration).
**Frequency:** rare. **Impact:** disk and patience.
**Handling:** refused from the metadata: "This video is longer than 6 hours, which is sukoon's limit." or "This video is bigger than 8 GB, which is sukoon's limit." The limits are the same ones uploads have.
**Verification:** unit tests on `refusal()`.

### DRM, or a stream sukoon doesn't fetch
**Scenario:** the formats are copy-protected, or offered only over a protocol yt-dlp would hand to another program (RTMP, for example).
**Frequency:** rare. **Impact:** nothing usable.
**Handling:** "This video is protected against copying (DRM), so it can't be fetched." or "This video is only offered as a kind of stream sukoon doesn't fetch."
**Verification:** unit tests on `refusal()`.

### Network drop
**Scenario:** the connection fails during the metadata request or the download.
**Frequency:** rare but real. **Impact:** a half-downloaded file.
**Handling:** yt-dlp retries on its own first; then "The connection dropped while fetching. Check your connection, then retry." The partial parts are deleted, and Retry fetches again from the start.
**Verification:** unit test on `explain()` with yt-dlp's DNS failure text.

### Out-of-date reader
**Scenario:** the site changed its pages and the pinned yt-dlp can no longer read them, or the site turned away a request that did not come from a browser (TikTok does this today).
**Frequency:** common over months. **Impact:** links from that site stop working.
**Handling:** "yt-dlp couldn't read this TikTok page. Its reader may be out of date, or TikTok turned the request away. To update it, run: uv lock --upgrade-package yt-dlp --upgrade-package yt-dlp-ejs && uv sync". `sukoon doctor` warns once yt-dlp is 60 days old. Nothing updates itself.
**Verification:** unit test on `explain()` with yt-dlp's "please report this issue" wording; doctor tests on the age line.

### A post that links somewhere else
**Scenario:** a Reddit or X post whose video lives on another site.
**Frequency:** rare but real. **Impact:** traffic to a site the user did not paste.
**Handling:** only the pasted site's extractors may run, so the hop is refused: "This post points to a video on another site. Open it there and paste that link."
**Verification:** unit test on `explain()`.

### A fetch that hangs or crashes
**Scenario:** yt-dlp stops making progress, or its process dies.
**Frequency:** rare. **Impact:** a job stuck in Fetching.
**Handling:** the download runs in its own child process. Ten minutes without a word from it fails the job with "The download made no progress for 10 minutes, so it was stopped." A crash fails it with "The download stopped unexpectedly." Cancel kills the child at once. If the app stops during a fetch, the job comes back interrupted and Retry fetches again.
**Verification:** tests with stand-in downloaders that stall, crash, and run across a restart.

## Separation

### The file has no music
**Scenario:** a plain voice recording.
**Frequency:** common. **Impact:** user wonders whether it worked.
**Handling:** the removed lane is nearly flat. When the removed energy is below 1% of the input energy the result says "There was almost no music in this file."
**Verification:** real-model test on speech only.

### The file has no voice
**Scenario:** an instrumental track.
**Frequency:** common. **Impact:** near-silent output.
**Handling:** when the kept voice is below -50 dBFS RMS overall, the result says "No voices were found; the output is nearly silent." The output is still produced.
**Verification:** real-model test on the music-only fixture.

### Singing, humming, vocal percussion
**Scenario:** a song with lyrics, a nasheed with vocal beat effects.
**Frequency:** common. **Impact:** the user expected them gone.
**Handling:** kept, by design (see `docs/adr/0002-keep-all-voices.md`). The empty state and the README say "voices stay".
**Verification:** documented behaviour; no test.

### GPU runs out of memory
**Scenario:** another app is holding VRAM, or a large model on a 4 GB card.
**Frequency:** rare but real. **Impact:** job failure.
**Handling:** a CUDA out-of-memory error on a chunk empties the CUDA cache and retries that chunk on CPU; later chunks try the GPU again. The job notes "Part of this ran on the CPU because the GPU ran out of memory."
**Verification:** worker test with an engine that raises `torch.cuda.OutOfMemoryError` on the first call.

### No GPU, or the CPU build of torch on a GPU machine
**Scenario:** torch installed without CUDA, or an old driver.
**Frequency:** common on first setup. **Impact:** slow runs with no explanation.
**Handling:** the status line shows the actual device. `sukoon doctor` says when an NVIDIA GPU is present but torch cannot use it and prints the install command for the CUDA build.
**Verification:** doctor test with torch's CUDA availability mocked.

### The worker process crashes
**Scenario:** a native crash inside torch or a driver reset.
**Frequency:** rare. **Impact:** the server must not go down with it.
**Handling:** the runner sees the child exit, fails the job with "The separation engine stopped unexpectedly", and starts a fresh worker for the next job. Retry works.
**Verification:** test with an engine that calls `os._exit(1)` mid-job: job fails, next job succeeds.

## Models

### First run, model not downloaded
**Scenario:** the user drops a file before any model exists.
**Frequency:** every new install. **Impact:** a 913 MB wait with no explanation.
**Handling:** the model card appears above the queue with both choices (download Best, or start with Fast). The job waits in "Waiting for model". Download progress shows bytes and speed.
**Verification:** API test with a fake download source.

### Offline during the first download, or the host is down
**Scenario:** no network, GitHub returns 5xx, the connection drops at 60%.
**Frequency:** rare but real. **Impact:** stuck first run.
**Handling:** downloads go to a `.part` file and resume with an HTTP Range request. Errors show "Couldn't download the model. Check your connection, then retry." with a Retry button. After download the app never needs the network.
**Verification:** test with a local HTTP server that drops the connection halfway, then resumes.

### Model file corrupted or replaced
**Scenario:** a partial file renamed by hand, disk corruption, or a tampered release asset.
**Frequency:** extremely rare. **Impact:** code execution risk or garbage output.
**Handling:** SHA-256 checked after every download and before every first load in a process. A mismatch deletes the file and fails with "The model file didn't match its expected checksum and was removed."
**Verification:** test that flips one byte in a fixture model file.

## Output

### The chosen container cannot hold the video codec
**Scenario:** VP9 into MOV, or ProRes into WEBM.
**Frequency:** rare. **Impact:** mux failure.
**Handling:** the codec and container compatibility table decides before the job starts. Incompatible pairs show "The picture will be re-encoded to H.264 for MP4 (about as long as the video's duration on this machine)" and need a confirm. WEBM output re-encodes to VP9 only when the source is not VP8, VP9, or AV1.
**Verification:** unit tests on the compatibility table; one pipeline test that forces a re-encode.

### Subtitles that will not copy
**Scenario:** PGS image subtitles into MP4, or ASS into MP4.
**Frequency:** rare. **Impact:** mux failure.
**Handling:** text subtitles convert to `mov_text` for MP4 and MOV; subtitle streams that cannot convert are dropped, and the result says "Subtitles were left out because MP4 can't hold them; choose MKV to keep them."
**Verification:** pipeline test with `subs-ass.mkv` to MP4 and to MKV.

### Audio offset against video
**Scenario:** the source audio starts 0.5 s after the video, or the AAC encoder adds priming samples.
**Frequency:** common in edited exports. **Impact:** lips out of sync.
**Handling:** the source audio stream's `start_time` is applied to the new audio at mux time, and AAC output is written through ffmpeg's mp4 muxer so the edit list hides the priming.
**Verification:** pipeline test with `offset-0.5s.mp4`: output audio start time within 1 ms of the source, and cross-correlation of output and source speech peaks at lag 0 plus or minus 1 ms.

### Output name problems
**Scenario:** names with Arabic, emoji, reserved Windows characters (`<>:"/\|?*`), trailing dots, or 200 characters.
**Frequency:** common. **Impact:** download fails or the name is mangled.
**Handling:** names are never used on disk. The download name is the original with reserved characters replaced by `-`, trailing dots and spaces stripped, and cut to 150 characters before ` (no music).ext`, sent with RFC 6266 `filename*=UTF-8''...`.
**Verification:** unit tests on the name function with each of those inputs.

### Transcoding a lossy file to the same lossy format
**Scenario:** MP3 in, MP3 out.
**Frequency:** common. **Impact:** a second generation of compression loss.
**Handling:** encoded at high quality (MP3 VBR V0, AAC 256 kbps, Opus 160 kbps, Vorbis q6) so the loss is not audible; FLAC and WAV are offered for anyone who wants none.
**Verification:** format matrix test checks encoder settings.

## Queue and lifecycle

### Upload interrupted
**Scenario:** the tab closes or the network drops halfway through an upload.
**Frequency:** rare (loopback). **Impact:** orphaned partial file.
**Handling:** uploads stream to a `.part` file that is deleted when the request ends without completing. A startup sweep removes any `.part` older than an hour.
**Verification:** API test that aborts a streaming upload.

### Tab closed while processing
**Scenario:** the user closes the browser.
**Frequency:** common. **Impact:** none, if handled.
**Handling:** processing is server-side and continues. Reopening the page shows the current state.
**Verification:** API test: start a job, disconnect the events stream, reconnect, state is current.

### App stopped while processing
**Scenario:** Ctrl+C, a restart, a power cut.
**Frequency:** rare but real. **Impact:** lost progress.
**Handling:** on startup, every job in a running state becomes `interrupted` and its scratch folder is deleted. Retry starts it from the beginning.
**Verification:** test that seeds the database with a running job and starts the app.

### Cancel while separating
**Scenario:** the user cancels a long job.
**Frequency:** common. **Impact:** must actually stop.
**Handling:** between chunks the worker checks a cancel flag. If a chunk takes longer than 20 seconds to respond, the runner terminates the worker and starts a new one. Cancel while encoding kills the ffmpeg process. The job ends `canceled` with its scratch folder deleted.
**Verification:** test with a slow fake engine: cancel lands within one chunk; with a hung engine: worker terminated within 25 s.

### Disk fills up mid-job
**Scenario:** something else fills the disk.
**Frequency:** rare. **Impact:** corrupt output.
**Handling:** any `ENOSPC` fails the job with "The disk is full." and deletes its scratch and partial output. Outputs are written to a temporary name and renamed only when complete, so a full disk never leaves a broken file that looks finished.
**Verification:** test that patches the writer to raise `OSError(ENOSPC)`.

### Two tabs
**Scenario:** the app is open twice.
**Frequency:** common. **Impact:** state drift.
**Handling:** all state lives on the server; both tabs receive the same events. Actions are idempotent (cancelling a canceled job is a no-op).
**Verification:** API test with two event-stream clients.

### Port already in use
**Scenario:** another program holds 8417, or sukoon is already running.
**Frequency:** common. **Impact:** startup failure.
**Handling:** if 8417 answers `/api/health` as sukoon, the browser is opened on it and the new process exits. Otherwise the next free port up to 8427 is used and printed.
**Verification:** CLI test with a dummy listener on 8417.

## Setup

### ffmpeg missing
**Scenario:** fresh machine.
**Frequency:** every new install. **Impact:** nothing works.
**Handling:** startup check; the interface shows one blocking screen with the install command for the platform (`winget install Gyan.FFmpeg`, `brew install ffmpeg`, `sudo apt install ffmpeg`) and a Check again button. `sukoon doctor` prints the same.
**Verification:** test with `PATH` emptied.

### ffmpeg without an encoder
**Scenario:** a minimal ffmpeg build without libmp3lame or libopus.
**Frequency:** rare. **Impact:** a format fails at the end of a long job.
**Handling:** encoders are checked at startup with `ffmpeg -encoders`; formats whose encoder is missing are disabled in the menu with a tooltip naming the missing encoder.
**Verification:** test with a patched encoder list.

### Windows paths
**Scenario:** user folders with spaces, non-ASCII characters, or long paths.
**Frequency:** common. **Impact:** subprocess failures.
**Handling:** every subprocess gets an argument list (no shell). The data folder path is resolved once and printed by `doctor`. Paths are built with `pathlib`.
**Verification:** test with `SUKOON_HOME` set to a folder named with Arabic letters and spaces.

## Browser and player

### Codec the browser cannot play
**Scenario:** HEVC in Firefox, ProRes anywhere.
**Frequency:** common for phone video. **Impact:** a black player.
**Handling:** the video element's `error` event switches to the audio-only strip with "Your browser can't preview this video; the downloaded file is fine."
**Verification:** component test firing `error` on the video element.

### Compare playback drift
**Scenario:** the cleaned and original audio elements play side by side for minutes.
**Frequency:** common. **Impact:** the compare switch jumps.
**Handling:** both audio previews come from the same decoded timeline. The muted one follows the audible one: every 250 ms, if they differ by more than 40 ms, the follower's `currentTime` is set. A seek takes time to land, so each follower learns from where its last correction landed how far ahead to aim, up to 250 ms; a jump bigger than that is the user seeking and teaches nothing. Video, when present, is the clock and both audio elements follow it.
**Verification:** component test with fake media elements advancing at different rates.

### Keyboard and screen reader
**Scenario:** a user who does not use a mouse, or uses NVDA.
**Frequency:** real. **Impact:** cannot use the app.
**Handling:** a visible "Choose files" button as the alternative to dropping; every row and control in tab order; the queue is a list with each row's name, state, and percentage as its accessible description; progress updates go through a polite live region at most every 10%; C to compare is also available as the switch.
**Verification:** keyboard-only pass in the browser verification; axe-core run on the main states.

### Narrow window
**Scenario:** the browser window is 375 px wide.
**Frequency:** rare for a desktop tool. **Impact:** clipped controls.
**Handling:** the row collapses to two lines (name and actions on one, stage and progress on the other); the settings sheet goes full width; no horizontal scroll.
**Verification:** screenshots at 375, 768, 1440.

### Local storage unavailable
**Scenario:** theme preference cannot be saved.
**Frequency:** rare. **Impact:** none, if handled.
**Handling:** every local storage access is wrapped; the app falls back to the system theme.
**Verification:** component test with `localStorage` throwing.
