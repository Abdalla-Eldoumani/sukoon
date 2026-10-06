# Glossary

**Job.** One input file going through sukoon, from upload to output, with its state and its files.
Avoid: task, conversion, request.

**Voice.** Everything the separation model keeps: speech, recitation, singing, humming, vocal percussion.
Avoid: vocals (except when naming a model), dialogue, speech (when you mean all of it).

**Removed.** The part of the input that is not voice: instruments, and with them most ambience and sound effects. Computed as the input minus the voice.
Avoid: instrumental, background, music track.

**Preset.** A named choice of separation model. Best and Fast exist.
Avoid: mode, quality level, engine.

**Engine.** The code behind the worker that turns a mixture chunk into a voice chunk. The real engine wraps audio-separator; tests use a fake one.
Avoid: separator (ambiguous with the library), backend.

**Worker.** The child process that hosts the engine and keeps the model loaded.
Avoid: daemon, service.

**Chunk.** A 60-second window of decoded audio, with 4 seconds of overlap on each side, separated in one engine call.
Avoid: segment (the library uses that word for something smaller), block.

**Strip.** The two waveform lanes on the review panel: voice above the center line, removed below.
Avoid: visualizer, spectrogram.

**Compare.** Playing the original audio in place of the cleaned audio at the same moment.
Avoid: A/B (in the interface), toggle.

**Data folder.** The one directory sukoon reads and writes, holding uploads, scratch, outputs, the database, and models.
Avoid: cache, app dir.
