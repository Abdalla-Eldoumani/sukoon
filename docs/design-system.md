# Design system

Every value the interface uses is in this file. If a component needs a value that is not here, the file gets updated first.

## Direction

```
Direction:  Meter bridge (the retro-futurist instrument family, pushed into the strip)
Is not:     not a stack of cards, not a dashboard of widgets, not skeuomorphic
Signature:  every file carries its own strip. A finished row is its two-lane miniature drawn from
            real peaks, voice kept above in amber and music removed below in steel; a running row
            shows how far into the recording the work has reached, in time, not percent. Review
            opens that same evidence at full size under the row.
Dials:      boldness 6/10, motion 3/10
Bar:        iZotope RX 11 (repair tools), Ableton Live 12 (dense audio UI that stays calm), Linear (lists whose columns never move)
Reason:     people trust a tool that removes things when it shows what it removed, so the
            evidence is the composition, drawn like a meter, and nothing decorative competes with it
```

Rules that follow from the contract.

- Every indicator shows live data or is not drawn.
- Amber means the voice that stays and nothing else: not progress, not focus, not buttons. Steel means what was taken out and nothing else. Neither ever needs a legend after the first strip.
- Progress, focus, and the one primary button use the ink color.
- There is one primary action on screen at a time.
- Rows are bands across the window, separated by hairlines, not cards.
- Labels are sentence case. Nothing is set in tracked capitals.

## Colors

The app follows the operating system theme and has a manual toggle. Dark is the reference theme: warm graphite. Light is the same panel by daylight: cool aluminium, never cream.

### Dark

| Token | Hex | CSS var | Use |
| --- | --- | --- | --- |
| ground | #12110F | --ground | Page, rows |
| band | #1C1B18 | --band | Selected row, review panel, fields, the settings sheet |
| rule | #2F2D28 | --rule | Hairlines between rows, lane center lines, empty tracks |
| edge | #6B675D | --edge | Borders of fields, quiet buttons, and switches |
| text | #EEEBE3 | --text | Primary text, progress, playhead |
| text-2 | #A8A396 | --text-2 | Secondary text, metadata |
| ink | #EEEBE3 | --ink | Primary button fill, focus ring, drag frame |
| on-ink | #12110F | --on-ink | Text on the primary button |
| voice | #F0A23A | --voice | The voice lane, and its label |
| removed | #7C97A8 | --removed | The removed-music lane, and its label |
| fault | #EF6F5E | --fault | Errors |
| scrim | rgba(18, 17, 15, 0.72) | --scrim | Behind the settings sheet |

Contrast (WCAG 2.2): text on ground 15.84, on band 14.46. text-2 on ground 7.50, on band 6.84. voice on ground 8.93, on band 8.15. removed on ground 6.15, on band 5.62. fault on ground 6.39, on band 5.83. on-ink on ink 15.84. edge on ground 3.35, on band 3.05 (control boundaries need 3). Rule on ground is 1.37 and is decorative only; no control relies on it.

### Light

| Token | Hex | CSS var | Use |
| --- | --- | --- | --- |
| ground | #ECECE8 | --ground | Page, rows |
| band | #E0E0DA | --band | Selected row, review panel, fields, the settings sheet |
| rule | #C9C9C1 | --rule | Hairlines |
| edge | #7A7A70 | --edge | Borders of fields, quiet buttons, and switches |
| text | #191A18 | --text | Primary text, progress, playhead |
| text-2 | #4A4B44 | --text-2 | Secondary text |
| ink | #191A18 | --ink | Primary button fill, focus ring, drag frame |
| on-ink | #ECECE8 | --on-ink | Text on the primary button |
| voice | #A15F00 | --voice | The voice lane (graphic) |
| voice-text | #7A4700 | --voice-text | The voice lane's label (text) |
| removed | #46606F | --removed | The removed-music lane, and its label |
| fault | #AE3226 | --fault | Errors |
| scrim | rgba(236, 236, 232, 0.72) | --scrim | Behind the settings sheet |

Contrast: text on ground 14.75, on band 13.18. text-2 on ground 7.45, on band 6.65. voice (graphic only) on ground 4.27, on band 3.82. voice-text on ground 6.50, on band 5.81. removed on ground 5.61, on band 5.01. fault on ground 5.40, on band 4.82. on-ink on ink 14.75. edge on ground 3.66, on band 3.27. In dark, `--voice-text` equals `--voice`.

Amber and steel are close in lightness (1.45 dark, 1.31 light), so they are never the only difference between two things: the lanes sit on opposite sides of a line, and each lane is labelled in words.

## Typography

### Faces

- **Archivo** (variable, `@fontsource-variable/archivo`, width axis from `wdth.css`): all interface text, using the width axis: 125 for the wordmark, 112 for the empty-state line, 87 for file names, 100 for everything else.
- **Martian Mono** (variable, `@fontsource-variable/martian-mono`, `wdth.css`) at width 87.5: every number that changes (times, durations, sizes, bytes). Tabular by design, so counting digits never jitter.
- **IBM Plex Sans Arabic** (`@fontsource/ibm-plex-sans-arabic`, the Arabic subset at 400, 500, and 600): the Arabic half of the wordmark, سكون, and any Arabic in a file name. Its `unicode-range` keeps it to Arabic letters, so Latin text never falls into it.
- Stack: `'Archivo Variable', 'IBM Plex Sans Arabic', 'Segoe UI', system-ui, sans-serif`. File names render with `dir="auto"` on their own block, so an Arabic name orders and truncates itself right to left; it still lines up on the left with the other names.

Fonts are bundled with the app. Nothing loads from a font CDN.

### Scale

| Token | Face | Size | Line height | Tracking | Weight | Width |
| --- | --- | --- | --- | --- | --- | --- |
| wordmark | Archivo, Plex Sans Arabic | 20px | 1 | 0.01em (Latin) | 700 Latin, 500 Arabic | 125 |
| display | Archivo | clamp(30px, 2.6vw + 14px, 44px) | 1.08 | -0.02em | 640 | 112 |
| title | Archivo | 18px | 1.3 | 0 | 600 | 100 |
| name | Archivo | 16px | 1.3 | 0 | 560 | 87 |
| body | Archivo | 15px | 1.5 | 0 | 400 | 100 |
| body-strong | Archivo | 15px | 1.5 | 0 | 560 | 100 |
| small | Archivo | 13px | 1.45 | 0 | 400 | 100 |
| readout | Martian Mono | 13px | 1.35 | 0 | 450 | 87.5 |
| readout-strong | Martian Mono | 15px | 1.3 | 0 | 450 | 87.5 |
| readout-lg | Martian Mono | 26px | 1.1 | -0.01em | 450 | 87.5 |

Nothing is smaller than 12px; 12px is used only for the strip's time ruler. Prose is held to 60 characters a line.

## Spacing and layout

Base unit 4px. Tokens: --s1 4px, --s2 8px, --s3 12px, --s4 16px, --s5 20px, --s6 24px, --s8 32px, --s12 48px, --s16 64px.

- Side gutter (`--gutter`): 48px from 1024px wide, 24px from 600px, 16px below. Bands run edge to edge; their content sits inside the gutter.
- Content is capped at 1440px wide, centered, so a very wide window does not stretch a strip past reading.
- Top bar: 64px tall, a hairline under it.
- Queue row: at least 76px tall, 14px vertical padding, a hairline under it. Columns, always in these tracks: glyph 20px, name up to 340px, lane the rest (at least 120px), time 184px (room for "1:02:44 of 1:30:00"), actions 84px, with 20px between them; below 1024px the name and the lane split the width evenly and the time track is 176px. A row with choices or a failure reason, and nothing to draw in its lane, lets the name column take the lane's track. Under 600px the row stacks: glyph, name, and actions on the first line; the lane and the time on the second.
- Review panel: a --band region under its row, 24px padding top and 32px bottom; video and strip side by side (video 420px) from 1024px wide, stacked below.
- Intake: starts 18vh down (10vh under 600px).

## Radius and borders

| Token | Value | Use |
| --- | --- | --- |
| --r-sm | 3px | Buttons, fields, selects, segmented controls, switches |
| --r-xs | 2px | The video frame, the playhead cap, a switch's knob |

Nothing else is rounded. Borders are 1px: --edge for anything you can operate, --rule for dividers. Elevation is flat: surfaces separate by tone and hairlines, never by shadow. The settings sheet sits over a --scrim and has a 1px --rule border on its leading edge; it has no shadow.

Focus: 2px solid --ink, offset 2px, on every focusable element, keyboard focus only (`:focus-visible`).

## Motion

CSS only. Movement uses only `transform` and `opacity`; hover and state colors change over 160ms.

- Easing out (entrances, settling): `cubic-bezier(0.2, 0, 0, 1)`. Easing in (exits): `cubic-bezier(0.4, 0, 1, 1)`.
- 90ms: the switches' detent, a button's 1px press.
- 160ms: hover and color changes; a row arriving (4px rise and fade); a stage word changing (fade in).
- 240ms: progress, a `transform` with a linear curve, so it glides between server updates; the settings sheet sliding in 24px and fading, and its scrim fading; the review panel opening and closing as a cross-fade, easing out, through the View Transitions API where the browser has it (an instant swap where not).
- 400ms: a strip drawing in, once, left to right, when a job finishes while the page is open: a --ground (or --band) cover over the lanes scales from 1 to 0 toward the right, easing out. It is the only flourish.
- Nothing fades in on page load, and nothing moves on its own.
- `prefers-reduced-motion: reduce` sets every duration to 0 and skips the draw-in.

## Components

Every component has default, hover, focus-visible, active, and disabled states, and where relevant loading, empty, error, and success. Hover confirms (the fill or text steps up); it never fades a control.

- **Top bar.** Wordmark at the left: "sukoon" then سكون in --text-2, 12px apart, both 20px. At the right: the device as a small --text-2 label and a readout (the server's "CUDA · GeForce RTX 3060 Laptop" becomes the label "CUDA" and the readout "GeForce RTX 3060 Laptop"; "CPU" becomes "Device" and "CPU"), the library size the same way ("Library 412 MB"), and the settings icon button. Under 600px the labels drop, the library readout goes (Settings shows it under Storage), and the device readout truncates.
- **Primary button.** Fill --ink, text --on-ink, body-strong, 44px tall with 22px horizontal padding (40px with 16px, the small size, in the queue's intake bar and beside selects), --r-sm. Hover: fill steps 12% toward --text-2. Active: translateY(1px). Disabled: --band fill, --text-2 text. Loading: the label stays and the button is disabled. One per screen: Choose files when the queue is empty, Download in an open review, Check again on the setup screen, Download Best on the model card when nothing else is primary (otherwise it is drawn quiet).
- **Quiet button.** Transparent, text --text, 1px --edge border, same sizes. Hover: --band fill. Icon-only quiet buttons are 36 by 36 with an `aria-label` and a title.
- **Text field** (the link field): native `<input type="url">`, 44px (40px in the intake bar), --band fill, 1px --edge border, --r-sm, 14px padding, placeholder --text-2. Hover: border --text-2. Invalid: `aria-invalid`, and the sentence under it in small --fault, tied with `aria-describedby`.
- **Select** (output format, track, default formats): native `<select>`, 40px, --band fill, 1px --edge border, --r-sm. Buttons beside a select (Continue, Re-encode) use the 40px small size.
- **Segmented control** (quality, device, theme): a row of segments in a 1px --edge frame; the selected one has --ground fill (it sits on the --band sheet), --text, and a 2px --ink underline; the others --text-2. Arrow keys move the choice.
- **Remove music switch** (link rows, until the job is checked): a 36 by 20 track with a 1px --edge border and a 12px knob, in the same detent as the Original switch, followed by "Remove music" in small text. `role="switch"`, accessible name "Remove music from" plus the file name. Off, the label stays the same and the row's line says "download only".
- **Intake (empty).** No box. Left-aligned in the gutter: the display line "Drop a recording anywhere on this window.", one sentence in --text-2, body size ("Voices stay and the music goes, all on this computer; a link from YouTube, X, Instagram, TikTok, Facebook, Reddit, Vimeo, or SoundCloud is fetched from its site, then cleaned here."), then the primary "Choose files", "or", the link field (420px), and a quiet "Add link". Nothing else. While a drag is over the window, the line reads "Release to add." and the window shows a 2px --ink inset frame. No dashed borders.
- **Intake bar (queue).** A row above the queue with a hairline under it: "Drop more files anywhere" in body-strong (hidden below 1024px), quiet "Choose files", the link field (it takes the room left, up to 480px with its button), quiet "Add link", and at the far right quiet "Clear finished" (which asks "Clear 3 finished jobs and their files?" in place, with Clear and Keep). Every button in the bar is the 40px small size.
- **Queue row.** A band on --ground with a hairline under it. Name column: the file name (name style, on one line, cut at its end with an ellipsis when it runs out of room; the whole name stays in the text, so it is read out in full, and in `title`; the format is on the line under it), then one small --text-2 line: the stage word in --text followed by what it is doing ("Separating", "Waiting, becomes MP3", "Done, MP3"); a link adds where it is from and that it was checked ("from youtube.com, checked as real video"), and "download only" when music removal is off. Choices (track, format, re-encode, Remove music) sit under that line. A failed row's reason replaces the line, in small --fault. Lane column: see Lane. Time column, right-aligned readouts: while decoding, separating, or encoding, how far that pass is through the recording and the total ("17:44 of 30:34"; the server sends the pass's own fraction, since overall progress is weighted across the passes) in readout-strong over the time left ("1:36 left") in readout --text-2; while fetching, the bytes ("31 MB of 74 MB", "1.20 GB of 2.50 GB", or "1 MB so far" without a total); while uploading, the share sent ("37%"); otherwise the duration. The file name, when it opens the review, underlines on hover with a 3px offset. Actions: Cancel while it can be stopped; Download and Delete when done; Retry and Delete when stopped. Selected (review open): --band. The glyph is audio, video, or link (while a link's kind is unknown).
- **Lane.** 40px tall, the row's own strip. Done with a cleaned result: the miniature strip, voice above and removed below a 1px gap, drawn from the job's peaks with bars 1px wide every 2px. Working: a 2px --rule line with the done part in --text and a 2px by 16px --text marker at the point reached; it glides. Fetching: the same line in bytes. Waiting, failed, stopped, or download only: the --rule line alone.
- **The strip** (review). A 20px time ruler (12px readout labels in --text-2, ticks at a round step of 1, 2, 5, 10, 15, or 30 seconds or whole minutes, at most one per 80px) over two lanes of 100px each with a 1px --rule line between them, voice above and removed below, on --band, bars 2px wide every 3px. A tick label that would run past the right edge is left out. Labels in words at the left, small, on a --band backing: "Voice kept" in --voice-text, "Music removed" in --removed. Playhead: 1px --text line with a 6px square cap on the ruler. Click or drag to seek; Left and Right move 5 seconds, Home and End jump, when it has focus.
- **Transport.** Play and pause (44px quiet icon button), the clock in readout-lg ("0:06 / 0:19", the total in --text-2), then the Original switch: "Clean" and "Original" in small text either side of a 46 by 24 track with a 16px knob that steps across in one 90ms detent (hover fills the track with --ground), and "hold C to compare" after it in small --text-2. Holding C, or holding the switch, plays the original only while held; a click toggles it. `role="switch"` with `aria-checked`. Download (primary) at the far right.
- **Review panel.** Opens under its row. Video and strip side by side from 1024px, so the strip is never under the fold; stacked below that, with the video at most 40vh tall. Audio jobs have the strip at full width.
- **Model download card.** A band under the intake, with a hairline under it: the title "The separation model downloads once", one sentence ("Best, 913 MB, is the cleaner, and the faster one on a graphics card. Fast, 67 MB, always runs on the processor, for computers without one."), the primary "Download Best (913 MB)" and a quiet "Start with Fast (67 MB)". While downloading: a 2px progress line, --text on --rule, and "322 MB of 913 MB at 16.3 MB/s". Its text is held to 60 characters a line.
- **Settings sheet.** Slides in from the right, 380px wide (full width under 600px), --band, over a --scrim that closes it on click. Groups with small --text-2 headings in sentence case: Quality ("Best is cleaner, and on a graphics card it is also the faster. Fast always runs on the processor."), Device, Default output format, Theme, Data folder (path in a readout, Open the cleaned files), Storage (sizes in readouts, Clear finished jobs).
- **Setup screen.** The top bar with the wordmark (no settings button), then the intake layout: the display line "sukoon needs ffmpeg.", one sentence, the command in a readout on --band with 12px by 16px padding, square, and the primary "Check again".
- **Errors.** Inline, next to what failed, in --fault, written as what happened plus what to do. Never a toast for an error.

## Iconography

A small hand-drawn SVG set, inlined as components, no icon library: 20px grid, 1.5px stroke, round caps and joins, `currentColor`. Set: audio file, video file, link, play, pause, download, cancel (x), retry (circular arrow), delete (bin), settings (three sliders), folder, chevron, check, warning. No other icons are added without adding them here.

## Imagery and texture

None. No photography, no illustration, no noise or grain. The waveforms are the only images.

## Copy

Plain, short, specific. Labels name the thing ("Download", not "Get your file"). Stages are verbs in the present: Uploading, Fetching, Checking, Decoding, Separating, Encoding. Numbers come with units. Times read as positions in the recording ("17:44 of 30:34"). No exclamation marks, no emoji.
