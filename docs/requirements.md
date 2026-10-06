# Requirements

## Summary

sukoon takes an audio or video file and gives it back with the music removed. Voices stay: speech, recitation, and singing. Everything runs on the user's own machine. Nothing is uploaded anywhere, and after the first model download it works offline.

## Goals

1. A user drops an MP3 or MP4 and gets the same kind of file back, with the instruments gone and the voices intact, without touching a terminal after setup.
2. Video output keeps the original picture untouched (no re-encode) and keeps the new audio in sync with it to within one millisecond.
3. The result can be checked before downloading: play it, flip to the original at the same moment, see where the music was.
4. It works on a laptop GPU (6 GB of VRAM) and still works, slower, on a CPU-only machine.
5. Nothing leaves the machine. No accounts, no telemetry, no cloud calls except downloading the models once from pinned addresses with pinned hashes.

## Non-goals

- Deployment. sukoon binds to `127.0.0.1` and is not meant to be exposed on a network or hosted.
- Removing singing. The separation keeps every human voice. Telling speech apart from singing is a different problem and is out of scope.
- Keeping sound effects. The models split voice from everything else, so ambient sound and effects go with the music. This is said plainly in the interface.
- Downloading from URLs (YouTube and similar). Users bring files.
- Editing: trimming, volume curves, captions. sukoon does one job.
- Mobile layouts beyond "usable". It is a desktop tool that should not break on a narrow window.

## User stories

- **A parent with a cartoon episode.** She drops a 22-minute MKV. The queue shows it decoding, then separating with a time estimate. When it finishes she scrubs to a song, holds the compare key, hears the music come back, lets go, hears only the characters singing. She downloads an MKV that plays in VLC with the original subtitles still there.
- **A student with a lecture recording.** He drops a two-hour MP3 with background music under the speaker. It runs on his CPU overnight. In the morning the file is waiting; the app was restarted in between and the finished job is still in the library.
- **Someone batch-cleaning short clips.** She drops twelve phone videos at once. They queue, run one after another, and she downloads each as it finishes. One of them has no audio track; it is rejected immediately with a sentence saying why, and the other eleven are not affected.

## Functional requirements

### Input

- Accepts any file ffmpeg can demux that has at least one audio stream: MP3, M4A, AAC, WAV, FLAC, OGG, Opus, WEBM, MP4, MOV, MKV, AVI and similar. Classification is by probing the content, never by extension.
- A file whose only video stream is attached cover art counts as audio.
- Playlist and indirection formats (HLS `.m3u8`, `concat`, `.txt`, `.sdp`, and anything else that points ffmpeg at other files or network addresses) are rejected before decoding.
- Files with more than one audio track show a picker; the default is the track marked default, else the first.
- Limits, each configurable: 8 GB per upload, 6 hours per file, 50 files waiting in the queue. Before accepting a file the server checks free disk space against an estimate of what the job will need and refuses with a clear message if it will not fit.

Acceptance: every fixture in the test corpus is either accepted and processed, or rejected before upload completes processing with a specific message (see `docs/behaviour.md`).

### Separation

- Two quality presets. **Best** uses the Mel-Band RoFormer vocal model by Kimberley Jensen (`vocals_mel_band_roformer.ckpt`, 913 MB). **Fast** uses `UVR-MDX-NET-Voc_FT.onnx` (67 MB). Best is the default.
- Models download on first use from their published GitHub release addresses into the app's data folder, with a visible progress bar, and are verified against pinned SHA-256 hashes before they are ever loaded. A mismatch deletes the file and fails loudly.
- Device selection: automatic (CUDA when available, else Apple MPS, else CPU), or forced CPU. When CUDA runs out of memory the chunk is retried on CPU and the user is told.
- Audio is processed in chunks so a six-hour file never needs six hours of audio in memory, progress moves smoothly, and cancelling takes effect within one chunk.

Acceptance, on the generated speech-over-music fixture: scale-invariant SDR of the output against the clean speech improves by at least 18 dB with Best and 15 dB with Fast; output length equals input length to the sample.

### Output

- Default output format matches the input container. The user can pick another: MP3, M4A (AAC), WAV, FLAC, Opus, OGG for audio; MP4, MKV, WEBM, MOV for video, or audio-only from a video.
- Video: the video stream is copied, never re-encoded, unless the chosen container cannot hold its codec; in that case the user is told before the job starts that the picture will be re-encoded and roughly how long that takes.
- Subtitles, chapters, container metadata, and cover art are carried across when the output container supports them. When a subtitle stream cannot be copied, the job finishes without it and says so.
- The output keeps the input's sample rate up to 48 kHz and its channel count up to stereo. Surround input is downmixed to stereo and the result says so.
- Output file name: the original name with ` (no music)` before the extension.

Acceptance: for each container pair in the test matrix, ffprobe shows the expected streams, the video stream's packets are byte-identical to the input's when copied, and the audio's start time and duration match the input within 1 ms.

### Queue and library

- Any number of files can be dropped at once; they run one at a time in drop order.
- Each job shows its stage (checking, decoding, separating, encoding), a progress bar, and once the first chunk is done a time estimate.
- Jobs can be cancelled while queued or running, retried after failure or cancellation, and deleted (which removes all of their files).
- Job state survives a restart. A job that was running when the app stopped comes back as interrupted, with a Retry button.
- Two tabs open on the app see the same queue and the same progress.
- The library shows how much disk space sukoon is using and has a button to clear finished jobs.

### Review

- Every finished job has a player. Audio jobs show two waveform lanes, voice kept and music removed. Video jobs show the video with the same lanes beneath it.
- A compare control, and the C key held down, switch playback to the original audio at the same position; releasing switches back. The switch is instant and the two sources never drift apart by more than one video frame.
- When the browser cannot play the video codec (HEVC or ProRes in some browsers, for example), the player falls back to the waveform with audio only and says that the downloaded file is unaffected.

### Setup and doctor

- `sukoon doctor` checks ffmpeg and ffprobe (and the encoders the output matrix needs), the torch device, free disk space, and which models are downloaded, and prints the exact install command for anything missing.
- `sukoon` starts the server on `127.0.0.1`, choosing the first free port from 8417 upward, and opens the browser.
- `sukoon clean <files...>` runs the same pipeline from the terminal, for scripting and for people who do not want the browser.

## Non-functional requirements

- **Privacy.** Server binds to `127.0.0.1` only. No analytics, no crash reporting, no fonts or scripts from a CDN. The only outbound requests are model downloads from the pinned addresses.
- **Security.** Requests with a `Host` header other than `127.0.0.1:<port>` or `localhost:<port>` are refused, which stops DNS-rebinding. State-changing requests whose `Origin` is not the app's own are refused, which stops other websites posting to the local server. ffmpeg runs with argument lists, never a shell, with its protocols limited to local files and pipes. Stored files use generated IDs, never user-supplied names.
- **Performance.** On an RTX 3060 Laptop GPU (6 GB) the target is at least 10 times faster than real time with Best. Measured on 2026-10-06: Best ran at 6.7 times real time on that GPU, short of the target but enough for one user (an hour of audio in about 9 minutes). Fast runs on the CPU, at 1.1 times real time on the same laptop and 0.45 times on a two-core sandbox.
- **Accessibility.** WCAG 2.2 AA contrast, full keyboard path through drop, queue, player, and download, visible focus, `prefers-reduced-motion` respected, screen-reader names on every control, progress announced politely.
- **Browsers.** Current Chrome, Edge, Firefox, Safari.
- **Platforms.** Windows 10 and 11 (primary), macOS on Apple Silicon, Linux. Python 3.12.

## Data handling

All data is the user's own and stays on their disk, in the app data folder (`%LOCALAPPDATA%\sukoon` on Windows, `~/Library/Application Support/sukoon` on macOS, `$XDG_DATA_HOME/sukoon` or `~/.local/share/sukoon` on Linux, or `SUKOON_HOME` when set). It holds uploads, intermediate audio, outputs, the job database, and the models. Intermediate audio is deleted when a job ends. Uploads and outputs stay until the user deletes the job or clears the library. Deleting a job removes every file it created.

## Success criteria

- Every acceptance criterion above passes in the automated suite, with the real-model tests passing on CPU.
- A manual run on the target Windows laptop processes one real music-over-speech video end to end on the GPU, and the result sounds clean to the person who asked for the tool.

## Open items

**Decisions** (each has a recommended answer; the build proceeds on the recommendation unless told otherwise):

- Project name `sukoon`. Recommended: keep.
- Keep finished jobs until deleted, rather than auto-deleting after some number of days. Recommended: keep, with storage use visible.

**Fog** (cannot be phrased precisely yet):

- Whether a dialogue, music, and effects separator would serve video users better than a voice separator. Revisit after real use shows how much people miss the sound effects.
- Whether an interface translation (Arabic first) is wanted.

**Out of scope for this release:** URL downloads, folders dropped as folders, editing, speech-only mode, hosting.
