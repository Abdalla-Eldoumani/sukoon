# Contributing

## Set up

Follow Install in the [README](../README.md), then install the interface's packages:

```bash
npm --prefix web ci
```

To work on the interface with live reload, run the server and Vite side by side, then open the address Vite prints. Vite passes `/api` through to the server.

```bash
uv run sukoon --no-browser   # terminal 1
npm --prefix web run dev     # terminal 2
```

`uv run python scripts/build_web.py` builds the interface and copies it into `sukoon/web_dist/`, which the server serves. Run it again after changing anything under `web/` if you use the server's own page.

## Layout

Two halves. `sukoon/` is the Python package: the server, the job queue, and everything that touches media. `web/` is the React interface. Nothing in the interface does media work; it shows what the server sends and asks it to act.

### `sukoon/`

| Folder | What it holds |
| --- | --- |
| `media/` | ffmpeg and ffprobe: finding them (`tools.py`), running them (`ffmpeg.py`), checking a file (`probe.py`), which streams each container holds (`compat.py`), `decode.py`, `encode.py`, `mux.py`, and download names (`naming.py`) |
| `separation/` | The models and their pinned hashes (`models.py`), downloading them (`download.py`), the engine that runs them (`engine.py`), 60-second chunks with crossfades (`chunk.py`), the worker process (`worker.py`), the device (`device.py`), `bench.py` |
| `links/` | The allowed sites and the address check (`sites.py`), every sentence a link job can fail with (`messages.py`), yt-dlp locked down in its child process (`ytdlp.py`), and the server side of a fetch (`fetch.py`) |
| `jobs/` | The SQLite store and its state machine (`store.py`), the runner thread that feeds the worker (`runner.py`), and the steps a job goes through (`pipeline.py`) |
| `server/` | The app and its security middleware (`app.py`), what every route shares (`services.py`), the job view the interface sees (`views.py`), receiving uploads and checking new files (`uploads.py`), link fetch threads (`fetches.py`), and `routes/`, one module per area of the API |
| `cli/` | The `sukoon` command (`main.py`), starting the server (`serve.py`), `clean` and `bench` (`clean.py`), `doctor.py` |

`settings.py` holds the limits and the data folder; `errors.py` holds the two exceptions a job can end with (cancelled, or failed with a sentence for the user).

### `web/`

| Folder | What it holds |
| --- | --- |
| `app/` | The entry point (`main.tsx`) and `App.tsx`, which holds the server state, the drag and paste handling, and the page layout |
| `components/queue/` | The empty page and the intake bar (`DropWell`, `EmptyStrip`), rows (`QueueRow`), their lanes (`Lane`), and the per-job choices (`JobChoices`) |
| `components/review/` | The review panel, its strip, and the transport with the Original switch |
| `components/chrome/` | The top bar, settings sheet, theme picker, setup screen, model card, and the live region that announces progress |
| `components/ui/` | The segmented control and the icons |
| `lib/api/` | The HTTP client, uploads, the live event stream, and the shared types |
| `lib/review/` | Keeping the cleaned and original audio in step (`sync.ts`), and loading and painting peaks (`lanes.ts`) |
| `lib/text/` | Times and sizes (`format.ts`), and the words for each state (`labels.ts`) |
| `lib/theme/` | The list of themes and choosing one |
| `styles/` | Every colour, one block per theme (`themes.css`), and the type, spacing, and controls (`global.css`) |
| `public/theme.js` | Sets the theme before the page paints |

Components are `PascalCase.tsx` with a `.module.css` beside them; everything else is kebab-case.

### Where to make common changes

| To change | Edit |
| --- | --- |
| A theme's colours | its block in `web/styles/themes.css` |
| The list of themes, their names and order | `web/lib/theme/themes.ts`, and the `ids` list in `web/public/theme.js` (a test checks they match) |
| A sentence a link job fails with | `sukoon/links/messages.py`; which yt-dlp error maps to it is `explain()` in `sukoon/links/ytdlp.py` |
| The sites links come from | `SITES` and `NAMES` in `sukoon/links/sites.py`, `REFUSED` in `messages.py`, and the README |
| An output format | `AUDIO_FORMATS` in `sukoon/media/encode.py`, or the container tables in `sukoon/media/compat.py` |
| A limit (size, length, queue) | `sukoon/settings.py` |
| A model | `MODEL_FILES` and its pinned hash in `sukoon/separation/models.py` |
| What a job shows the interface | `public()` in `sukoon/server/views.py`, and `web/lib/api/types.ts` |
| An API route | its area's module in `sukoon/server/routes/`; `server/router.py` lists them |

## Checks

These are the checks CI runs on every pull request. Run them before you push.

```bash
uv run ruff check
uv run ruff format --check
uv run mypy
uv run pytest -q
npm --prefix web run lint
npm --prefix web run typecheck
npm --prefix web test -- --run
npm --prefix web run build
```

## Tests

The Python tests generate their own media into `tests/fixtures/generated/` the first time they run (`scripts/make_fixtures.py`; they need ffmpeg and `espeak-ng`). They use a stand-in engine instead of the real models and a stand-in downloader instead of yt-dlp, so the default run needs no network and no GPU. Three sets are left out by default:

```bash
uv run pytest -q -m slow                            # a 70-minute file through the worker; Linux only (reads /proc)
SUKOON_TEST_MODELS=1 uv run pytest -q -m model      # the real models; downloads about 1 GB
SUKOON_TEST_NETWORK=1 uv run pytest -q -m network   # one real link per site
```

`tests/test_queue.py::test_eta_is_close_to_the_real_remaining_time` checks the time estimate to within 25%, and can fail on a slow two-core machine.

The interface tests run in jsdom with Testing Library; `app/a11y.test.tsx` runs axe-core on the main states.

[behaviour.md](behaviour.md) names the test behind each failure case.

## Pull requests

- Branch off `integration` with a name that says what changes (`feat/theme-picker`, `fix/arabic-truncation`), and open the pull request into `integration`. `integration` goes to `main` in one pull request.
- One file per commit, with a short lowercase message that says what changed in the code.
- Keep changes small and covered by a test.
- Keep the rule that nothing leaves the user's computer except the pinned model downloads and the links the user pastes.
- Update the doc that describes what you changed in the same pull request.
