# sukoon

sukoon removes the music from audio and video files and keeps the voices: speech, recitation, and singing. Drop in a file or paste a link, and you get the same kind of file back without the music. It runs on your own computer and uploads nothing.

## What it does

- Keeps every human voice. Removes instruments and beats, and with them most other non-voice sound (ambience, effects, applause), because the models split voice from everything else. Separation is not exact: a little music can stay in the voice, and a voice can lose some of its own sound, so play the result against the original before you rely on it.
- Copies a video's picture untouched and puts the cleaned audio back in sync with it. Subtitles, chapters, other audio tracks, and metadata come along when the output format can hold them.
- Keeps the input's format unless you pick another: MP3, M4A, WAV, FLAC, Opus, or OGG for audio, MP4, MKV, WebM, or MOV for video.
- Shows each result as a strip, the voice kept above a line and the music removed below it, and lets you play the cleaned file and switch to the original at the same moment before you download.

It does not edit, trim, transcribe, or tell one voice from another. You're responsible for having the right to the media you process, including what you fetch by link under each site's terms.

## Install

You need:

- Windows 10 or 11 (x64), macOS on Apple Silicon, or Linux (x86-64)
- [uv](https://docs.astral.sh/uv/), which installs Python 3.12 by itself
- Node.js 22.13 or newer, to build the interface once and to read YouTube links
- ffmpeg and ffprobe on your PATH (the commands below install builds with every encoder sukoon uses)
- About 8 GB free for the packages and models, plus room for your files
- Optional: an NVIDIA GPU with 6 GB of memory and a driver for CUDA 12.6. Apple Silicon uses its GPU with no setup. Without either, sukoon runs on the processor, which is much slower.

**Windows** (in Git Bash; the steps from `git clone` on were checked on a machine that already had these four packages):

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

**macOS** (not tested on a Mac yet):

```bash
brew install uv node ffmpeg
git clone https://github.com/abdalla-eldoumani/sukoon.git
cd sukoon
uv sync
uv run python scripts/build_web.py
```

**Linux** (the automated checks run on Ubuntu 24.04):

```bash
sudo apt install ffmpeg
curl -LsSf https://astral.sh/uv/install.sh | sh
# install Node.js 22.13 or newer from nodejs.org or your package manager
git clone https://github.com/abdalla-eldoumani/sukoon.git
cd sukoon
uv sync
uv run python scripts/build_web.py
```

Then run `uv run sukoon doctor`. Its torch line names the device sukoon will use, for example `device CUDA · GeForce RTX 3060 Laptop`. If it says `NVIDIA GPU present but torch has no CUDA`, run `uv sync` again, then update the NVIDIA driver if it still says CPU.

## Use it

```bash
uv run sukoon                # opens http://127.0.0.1:8417/ in your browser
uv run sukoon --no-browser   # the same, without opening the browser
```

If port 8417 is taken, the next free one up to 8427 is used and printed. Starting sukoon twice opens the one already running. Press Ctrl+C in its terminal to stop it; a job that was running comes back as interrupted, with Retry.

- **Add files.** Drop them anywhere on the window, or press Choose files. Each file becomes a row, and they run one at a time.
- **Watch it work.** A running row shows how far into the recording it has got and the time left ("17:44 of 30:34, 1:36 left").
- **Check the result.** A finished row draws its strip. Click the file name to open the review: play it, and hold C (or the Original switch) to hear the original at the same moment.
- **First run.** The first job asks for a model: Best (913 MB) or Fast (67 MB). It downloads once, and waiting jobs start when it's ready.
- **Settings** (the sliders button): quality, device, default output formats, theme, and the data folder. The themes are System, Night, Day, High contrast, Parchment, and Midnight. System follows your computer's light or dark setting and switches to High contrast when the computer asks for more contrast.

## Links

Paste a link into the field, or press Ctrl+V anywhere outside a text field. sukoon takes single videos from YouTube, X, Facebook, Reddit, and SoundCloud, and tries Instagram, TikTok, and Vimeo. It refuses playlists, channels, and live streams, and says why.

A link row shows where the file comes from and how much has arrived, then runs like a dropped file. Remove music is on by default; turn it off on the row to download only. Either way the file becomes MP4 (H.264 and AAC where offered), or M4A when it has no picture, unless you pick another format.

sukoon never signs in to a site. As of October 2026, Vimeo gives nothing to requests that aren't signed in, Instagram gives the picture without the sound, and TikTok refuses requests that don't come from a browser; those jobs fail with a sentence saying so. YouTube, X, Facebook, Reddit, and SoundCloud worked in testing.

Sites change their pages every few weeks. When a job says the reader may be out of date, or `sukoon doctor` says yt-dlp is more than 60 days old, update it:

```bash
uv lock --upgrade-package yt-dlp --upgrade-package yt-dlp-ejs && uv sync
```

## The command line

```bash
uv run sukoon clean talk.mp3 --out cleaned/
uv run sukoon clean lecture.mkv --format mp4 --allow-reencode
uv run sukoon clean "https://www.youtube.com/watch?v=jNQXAC9IVRw"
uv run sukoon clean "https://soundcloud.com/..." --keep-music --format mp3
uv run sukoon doctor
uv run sukoon bench --preset best
```

| Command | What it does |
| --- | --- |
| `clean` | Runs files or links through the same steps as the browser and prints each result's path, such as `cleaned/talk (no music).mp3`. Options: `--preset best\|fast`, `--device auto\|cpu`, `--format`, `--track 2` (clean the second audio track), `--allow-reencode` (when the chosen container can't hold the picture as it is), `--keep-music` (download only), `--out` (results folder; by default next to each file, or the current folder for links). Quote links, since `&` and `?` mean something to the shell. |
| `doctor` | Checks ffmpeg and ffprobe and their encoders, torch and its device, free disk space, yt-dlp and its age, `yt-dlp-ejs`, Node.js, and the downloaded models. Prints a `fix:` line for anything missing and exits with 1 if something needs fixing. |
| `bench` | Separates a generated 30-second clip three times and prints how many times faster than real time it ran. |

## Speed and quality

On an RTX 3060 Laptop GPU, Best runs about 6.7 times faster than real time, so an hour of audio takes about 9 minutes. Fast always runs on the processor, at about 1.1 times real time on that laptop. On 90 seconds of speech under a beat at equal loudness, Best raised the speech's clarity (SI-SDR) from 0.3 dB to 18.1 dB and Fast to 16.1 dB. Fast also returns speech about 7 dB quieter than it went in, which Best does not. With an NVIDIA GPU, use Best.

## Where your files are

Everything sukoon stores is in one folder:

| System | Folder |
| --- | --- |
| Windows | `%LOCALAPPDATA%\sukoon` |
| macOS | `~/Library/Application Support/sukoon` |
| Linux | `$XDG_DATA_HOME/sukoon`, or `~/.local/share/sukoon` |

Set `SUKOON_HOME` to use another folder, for example on a bigger drive. Inside are `uploads/`, `outputs/`, `work/` (intermediate audio, deleted when each job ends), `models/`, and `jobs.db` (the jobs and settings). Files are stored under generated IDs; the friendly name, such as `talk (no music).mp3`, is used when you download. Deleting a job removes every file it made, Clear finished does that for every finished job, and deleting the folder removes everything.

## Privacy

- The server listens on `127.0.0.1` only, so other computers can't reach it, and it refuses requests from other websites.
- There are no analytics or crash reports, and no fonts or scripts load from the internet.
- Models download from the fixed addresses in `sukoon/separation/models.py`. Each file's size and SHA-256 are checked before it's used, and after that sukoon works offline.
- A link is fetched from its site only when you paste it. sukoon sends no cookies, uses no account, reads no browser data, and loads no code from the internet (the YouTube solver is installed with the app). The downloaded file gets the same check as a dropped file before anything opens it. That check confirms it's real audio or video; it is not a virus scan.

## Troubleshooting

Start with `uv run sukoon doctor`; every failing line comes with a `fix:` line.

| You see | Do this |
| --- | --- |
| `ffmpeg ... not found on PATH` | Install it with the printed command (`winget install Gyan.FFmpeg`, `brew install ffmpeg`, or `sudo apt install ffmpeg`), then open a new terminal. |
| `encoders missing ...` | Your ffmpeg lacks some encoders, so formats that need them are hidden. Install a full build to get them back. |
| `torch not installed` | Run `uv sync`. |
| `NVIDIA GPU present but torch has no CUDA` | Run `uv sync`. If it still shows CPU, update the NVIDIA driver. |
| `disk ... GB free` marked FAIL | Free space on that drive or set `SUKOON_HOME` to another one. A running job needs about 2.5 GB per hour of sound for intermediate audio. |
| A model download stopped | Press Retry on the model card; it resumes where it stopped. A file that fails its hash check is deleted and downloaded again. |
| "Part of this ran on the CPU because the GPU ran out of memory." | That part was redone on the processor, which is slower. Closing other programs that use the GPU helps. |
| A link fails | The job's sentence says why. "Its reader may be out of date" means run the update command under Links. A site that only shares with signed-in people can't be fetched; save the file another way and drop it in. |
| The page stops updating | Check that sukoon's terminal is still open. Start it again with `uv run sukoon` and reload; finished jobs are still there. |

## Credits

sukoon downloads and runs separation models made by other people, under their authors' terms:

- **Best**: the Mel-Band RoFormer vocal model by Kimberley Jensen ([KimberleyJSN/melbandroformer](https://github.com/KimberleyJSN/melbandroformer)), MIT license, built on the Mel-Band RoFormer architecture from ByteDance research. Downloaded from the python-audio-separator model mirror.
- **Fast**: UVR-MDX-NET Voc FT from [Ultimate Vocal Remover](https://github.com/Anjok07/ultimatevocalremovergui) by Anjok07 and the UVR team, MIT license. Downloaded from the UVR model repository.
- [python-audio-separator](https://github.com/nomadkaraoke/python-audio-separator) by Andrew Beveridge, MIT license, which loads and runs both models.
- [yt-dlp](https://github.com/yt-dlp/yt-dlp) (Unlicense) and `yt-dlp-ejs` (Unlicense, MIT, and ISC), which read the sites links come from.

The interface uses the Archivo, Martian Mono, and IBM Plex Sans Arabic typefaces (SIL Open Font License), bundled with the app.

## Contributing

[docs/contributing.md](docs/contributing.md) covers setup, the folder layout, the checks, and the tests. Every doc is listed in [docs/README.md](docs/README.md).

## License

MIT
