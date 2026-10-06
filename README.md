# sukoon

Drop in an audio or video file, get it back without the music. Voices stay: speech, recitation, and singing. Everything runs on your own computer, and nothing is uploaded anywhere.

This is being built. Full setup instructions land here once the first version runs end to end.

## Run it

You need [uv](https://docs.astral.sh/uv/), Node.js 22.13 or newer, and ffmpeg on your PATH.

```bash
python scripts/build_web.py     # builds the interface and copies it into the package
uv sync --extra cpu             # or --extra cuda on a machine with an NVIDIA GPU
uv run sukoon                   # starts on http://127.0.0.1:8417/ and opens the browser
uv run sukoon --no-browser      # same, without opening the browser
uv run sukoon doctor            # checks ffmpeg, encoders, torch, disk space, and models
```

`uv sync` has not been run on the machine this version was built on, because PyTorch's download host was unreachable there. The other commands were run, from a virtual environment holding every dependency except torch and audio-separator.

To work on the interface with live reload, run `uv run sukoon --no-browser` in one terminal and `npm --prefix web run dev` in another, then open the address Vite prints.

## What it does and doesn't do

- Keeps every human voice and removes the instruments. Most non-voice sounds (ambience, sound effects) go with them, because the models split voice from everything else.
- Copies the picture of a video untouched and swaps in the cleaned audio, in sync.
- Works on an NVIDIA GPU, on Apple Silicon, or on a plain CPU (slower).

The separation models are made by other people and downloaded from their release pages the first time you use them; they're credited in this README once it's finished. You're responsible for having the right to the media you process.

## License

MIT
