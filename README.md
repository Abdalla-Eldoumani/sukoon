# sukoon

Drop in an audio or video file, or paste a link, and get it back without the music. Voices stay: speech, recitation, and singing. Everything runs on your own computer, and nothing is uploaded anywhere.

## What it keeps and what it removes

- Keeps every human voice: speech, recitation, singing, background chatter.
- Removes instruments and beats. Most other non-voice sound (ambience, sound effects, applause) goes with them, because the models split voice from everything else.
- For video, the picture is copied untouched and the cleaned audio is put back in sync with it. Subtitles, chapters, other audio tracks, and metadata are carried across when the output container can hold them.
- The result keeps the input's format unless you choose another: MP3, M4A, WAV, FLAC, Opus, or OGG for audio; MP4, MKV, WebM, or MOV for video.

It does not edit, trim, transcribe, or separate one voice from another. You're responsible for having the right to the media you process, including what you fetch by link under each site's terms.

## Requirements

- Windows 10 or 11 (x64), macOS on Apple Silicon, or Linux (x86-64).
- [uv](https://docs.astral.sh/uv/), which installs the right Python (3.12) by itself.
- Node.js 22.13 or newer, to build the interface once.
- ffmpeg and ffprobe on your PATH, built with the usual encoders (libmp3lame, aac, libopus, libvorbis, flac, pcm_s24le, libx264, libvpx-vp9). The builds from the commands below have them.
- About 8 GB of free disk space for the Python packages and the models, plus room for your files.
- Optional: an NVIDIA GPU with 6 GB of memory or more and a driver new enough for CUDA 12.6. Apple Silicon Macs use their GPU without extra setup. Without either, sukoon runs on the CPU, which is much slower. The same install works with or without a GPU.

## Install

### Windows

In Git Bash:

```bash
winget install astral-sh.uv
winget install OpenJS.NodeJS.LTS
winget install Gyan.FFmpeg
winget install Git.Git
# open a new terminal so the PATH changes apply
git clone https://github.com/abdalla-eldoumani/sukoon.git
cd sukoon
uv sync
uv run python scripts/build_web.py
```

### macOS (Apple Silicon)

Not tested on a Mac yet.

```bash
brew install uv node ffmpeg
git clone https://github.com/abdalla-eldoumani/sukoon.git
cd sukoon
uv sync
uv run python scripts/build_web.py
```

### Linux

```bash
sudo apt install ffmpeg
curl -LsSf https://astral.sh/uv/install.sh | sh
# install Node.js 22.13 or newer from nodejs.org or your package manager
git clone https://github.com/abdalla-eldoumani/sukoon.git
cd sukoon
uv sync
uv run python scripts/build_web.py
```

### Checking the GPU

```bash
uv run sukoon doctor
```

The torch line shows the device sukoon will use, for example `device CUDA · GeForce RTX 3060 Laptop`. If it says `NVIDIA GPU present but torch has no CUDA`, run `uv sync` again, and if it still says CPU, update the NVIDIA driver.

## Running

```bash
uv run sukoon                # starts on http://127.0.0.1:8417/ and opens the browser
uv run sukoon --no-browser   # the same, without opening the browser
```

If 8417 is taken, the next free port is used and printed. Starting sukoon a second time opens the one already running.

Drop files anywhere on the window, choose them, or paste a link. Each one becomes a row. While it works, the row shows how far into the recording it has got and the time left ("17:44 of 30:34, 1:36 left"). When it finishes, the row draws what was kept, the voice in amber above the line, and what was removed, in steel below it. Click the file name to open the review: play it, hold C (or the switch) to hear the original at the same moment, and download the result. The first time a job needs a model, a card above the list offers Download Best (913 MB) or Start with Fast (67 MB); the model downloads once, and waiting jobs start when it is in place. Settings (the sliders button in the top bar) hold the model choice, the device, default output formats, and the theme.

To stop sukoon, press Ctrl+C in its terminal. A job that was running is marked interrupted and can be retried after the next start.

## Links

Paste a link into the field in the drop area, or press Ctrl+V anywhere on the page outside a text field. sukoon takes single videos from YouTube, X, Instagram, TikTok, Facebook, Reddit, Vimeo, and SoundCloud; playlists, channels, and live streams are refused with a sentence that says why.

The row shows where the file comes from and how much has arrived, then the same stages as a dropped file. Remove music is on by default. Turn it off on the row for download only: the file is converted to the format you pick, with every stream copied that the format can hold. A link becomes MP4 (H.264 and AAC where the site offers them), or M4A when it has no picture.

sukoon never signs in to a site. Some sites refuse requests like sukoon's, and the job says so: as of October 2026, Vimeo and Instagram's sound are only for signed-in people, and TikTok turns away requests that don't come from a browser. YouTube, X, Facebook, Reddit, and SoundCloud worked in testing.

Sites change their pages every few weeks, so a link that worked last month can stop working. When a job says the reader may be out of date, or `sukoon doctor` says yt-dlp is old, update it:

```bash
uv lock --upgrade-package yt-dlp --upgrade-package yt-dlp-ejs && uv sync
```

YouTube links also need Node.js 22 or newer, the same Node the install uses; `sukoon doctor` checks it.

## The command line

```bash
uv run sukoon clean talk.mp3 --out cleaned/
uv run sukoon clean lecture.mkv --format mp4 --allow-reencode
uv run sukoon clean "https://www.youtube.com/watch?v=jNQXAC9IVRw"
uv run sukoon clean "https://soundcloud.com/..." --keep-music --format mp3
uv run sukoon doctor
uv run sukoon bench --preset best
```

- `clean` runs the same steps as the browser on files or links and prints the path of each result, for example `cleaned/talk (no music).mp3`. Options: `--preset best|fast`, `--device auto|cpu`, `--format` (any output format above), `--track 2` to clean the second audio track, `--allow-reencode` when the chosen video container can't hold the original picture, `--keep-music` for download only, and `--out` for the results folder (by default, next to each file, and the current folder for links). Put a link in quotes, since `&` and `?` mean something to the shell.
- `doctor` checks ffmpeg, ffprobe, the encoders, torch and its device, free disk space, yt-dlp and its age, `yt-dlp-ejs`, Node.js, and which models are downloaded. It prints the fix for anything missing and exits with 1 if something needs fixing.
- `bench` times separation on a generated 30-second clip and prints how many times faster than real time it ran.

On an RTX 3060 Laptop GPU, Best runs about 6.7 times faster than real time, so an hour of audio takes about 9 minutes. Fast always runs on the CPU (about 1.1 times real time on that laptop) and is a 67 MB download instead of 913 MB. With an NVIDIA GPU, use Best. Fast is for computers without one; it also returns speech a little quieter than the original, which Best does not.

## Where files live

Everything sukoon stores is in one folder:

| System | Folder |
|---|---|
| Windows | `%LOCALAPPDATA%\sukoon` |
| macOS | `~/Library/Application Support/sukoon` |
| Linux | `$XDG_DATA_HOME/sukoon`, or `~/.local/share/sukoon` |

Set `SUKOON_HOME` to use another folder, for example on a bigger drive. Inside are `uploads/`, `outputs/`, `work/` (intermediate audio, deleted when each job ends), `models/`, and `jobs.db` (the job list and settings). Files are stored under generated IDs; the friendly name, such as `talk (no music).mp3`, is used when you download. Deleting a job removes every file it made, and Clear finished does that for all finished jobs. Removing the folder removes everything.

## Privacy

- The server listens on `127.0.0.1` only, so other computers can't reach it, and it refuses requests from other websites.
- No analytics, no crash reports, no fonts or scripts from the internet.
- Model downloads go to the fixed addresses in `src/sukoon/models.py`: the model files and three small tables of model settings that the separation library reads. Each file's size and SHA-256 hash are checked before it is used, and once they are downloaded sukoon works offline.
- When you paste a link, and only then, sukoon fetches it from that site and the site's media servers. It sends no cookies and no account, reads no browser data, and loads no code from the internet; the YouTube solver it uses is installed with the app. The downloaded file is checked to be real audio or video, the same check a dropped file gets, before anything else opens it. That check is not a virus scan.

## Troubleshooting

Start with `uv run sukoon doctor`; each failing line comes with a `fix:` line.

- **`ffmpeg ... not found on PATH`**: install it with the printed command (`winget install Gyan.FFmpeg`, `brew install ffmpeg`, or `sudo apt install ffmpeg`), then open a new terminal.
- **`encoders missing ...`**: your ffmpeg build lacks some encoders. Formats that need them are hidden in the app; install a full build to get them back.
- **`torch not installed`**: run `uv sync`.
- **`NVIDIA GPU present but torch has no CUDA`**: run `uv sync`. If it still shows CPU, update the NVIDIA driver.
- **`disk ... GB free`** marked FAIL: free space on that drive or set `SUKOON_HOME` to another one. While a job runs, its intermediate audio takes about 2.5 GB per hour of sound.
- **A model download stopped**: press Retry on the model card; the download resumes where it stopped. If a file fails its hash check it is deleted and downloaded again.
- **A job says "Part of this ran on the CPU because the GPU ran out of memory."**: that part of the file was redone on the CPU, which is slower. Closing other programs that use the GPU helps.
- **A link fails**: the job's sentence says why. "Its reader may be out of date" means updating yt-dlp with the command under Links; a site that only shares with signed-in people can't be fetched, so save the file another way and drop it in.
- **The page stops updating**: check that the terminal running sukoon is still open. Start it again with `uv run sukoon` and reload the page; finished jobs are still there.

## Credits

sukoon downloads and runs separation models made by other people, under their authors' terms:

- **Best**: the Mel-Band RoFormer vocal model by Kimberley Jensen ([KimberleyJSN/melbandroformer](https://github.com/KimberleyJSN/melbandroformer)), MIT license, built on the Mel-Band RoFormer architecture from ByteDance research. Downloaded from the python-audio-separator model mirror.
- **Fast**: UVR-MDX-NET Voc FT from the [Ultimate Vocal Remover](https://github.com/Anjok07/ultimatevocalremovergui) project by Anjok07 and the UVR team, MIT license. Downloaded from the UVR model repository.
- [python-audio-separator](https://github.com/nomadkaraoke/python-audio-separator) by Andrew Beveridge, MIT license, which loads and runs both models.

The interface uses the Archivo and Martian Mono typefaces (SIL Open Font License), bundled with the app.

## Contributing

The Python side needs the steps under Install; the checks below are the ones CI runs.

```bash
uv run ruff check
uv run ruff format --check
uv run mypy src
uv run pytest -q
npm --prefix web ci
npm --prefix web run lint
npm --prefix web run typecheck
npm --prefix web test -- --run
npm --prefix web run build
```

The tests generate their own media into `tests/fixtures/generated/` the first time they run (they need ffmpeg and `espeak-ng`). They use a stand-in engine instead of the real models. Two more sets are left out by default:

```bash
uv run pytest -q -m slow                         # a 70-minute file through the separation worker
SUKOON_TEST_MODELS=1 uv run pytest -q -m model   # the real models; downloads about 1 GB
```

To work on the interface with live reload, run `uv run sukoon --no-browser` in one terminal and `npm --prefix web run dev` in another, then open the address Vite prints.

How it is built, and why, is in `docs/`: `requirements.md`, `architecture.md`, `behaviour.md`, `design-system.md`, and the decision records in `docs/adr/`. Keep changes small and covered by a test, and keep the rule that nothing leaves the user's computer except the pinned model downloads.

## License

MIT
