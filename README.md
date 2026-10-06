# sukoon

Drop in an audio or video file, get it back without the music. Voices stay: speech, recitation, and singing. Everything runs on your own computer, and nothing is uploaded anywhere.

This is being built. Setup instructions land here once the first version runs end to end.

## What it does and doesn't do

- Keeps every human voice and removes the instruments. Most non-voice sounds (ambience, sound effects) go with them, because the models split voice from everything else.
- Copies the picture of a video untouched and swaps in the cleaned audio, in sync.
- Works on an NVIDIA GPU, on Apple Silicon, or on a plain CPU (slower).

The separation models are made by other people and downloaded from their release pages the first time you use them; they're credited in this README once it's finished. You're responsible for having the right to the media you process.

## License

MIT
