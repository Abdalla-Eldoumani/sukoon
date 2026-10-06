# Design system

Every value the interface uses is in this file. If a component needs a value that is not here, the file gets updated first.

## Direction

```
Direction:  Studio instrument (from the retro-futurist instrument family, without the costume)
Is not:     not skeuomorphic (no brushed metal, screws, or fake LEDs), not a SaaS dashboard
Signature:  the strip: two waveform lanes sharing one time ruler, voice kept above the line in amber,
            music removed below it in steel, with a detented Original switch beside the transport
Dials:      boldness 4/10, motion 3/10
Bar:        iZotope RX 11 (repair tools), Ableton Live 12 (dense audio UI that stays calm), Things 3 (list rows)
Reason:     the tool is an audio repair instrument; people trust it when it shows them what it removed,
            so the one memorable thing is the evidence, drawn like a meter, not a decoration
```

Rules that follow from the contract. Every indicator shows live data or is not drawn. Amber always means "the voice that stays" and steel always means "what was taken out"; neither color is used for anything else, so the colors never need a legend after the first time. Labels are engraved: small uppercase, tracked, quiet. There is one primary action on screen at a time.

## Colors

The app follows the operating system theme and has a manual toggle. Dark is the reference theme; light is a daylight version of the same panel, cool aluminium rather than cream.

### Dark

| Token | Hex | CSS var | Use |
| --- | --- | --- | --- |
| ground | #141513 | --ground | Page background |
| surface | #1C1D1A | --surface | Queue rows, panels |
| raised | #262723 | --raised | Wells, inputs, selected row, lane background |
| rule | #34352F | --rule | Hairlines, dividers, inactive tracks |
| text | #ECEAE3 | --text | Primary text |
| text-2 | #B4B1A6 | --text-2 | Secondary text, file metadata |
| text-3 | #8C897F | --text-3 | Engraved labels; on ground or surface only |
| voice | #F2A93B | --voice | Voice lane, progress fill, primary button fill, focus ring |
| removed | #7F9BAD | --removed | Removed-music lane |
| fault | #F0705F | --fault | Errors |
| on-voice | #191A18 | --on-voice | Text on a voice-filled control |

Contrast (WCAG): text on ground 15.22, on surface 14.07, on raised 12.49. text-2 on ground 8.53, on raised 7.00. text-3 on ground 5.23, on surface 4.84 (on raised 4.30, so it is not used there). voice on ground 9.17. removed on ground 6.28. fault on ground 6.27, on raised 5.15. on-voice on voice 8.74. Rule against surface is 1.37 and is decorative only; no control relies on it for its boundary.

### Light

| Token | Hex | CSS var | Use |
| --- | --- | --- | --- |
| ground | #E8E8E4 | --ground | Page background |
| surface | #F4F4F1 | --surface | Queue rows, panels |
| raised | #DCDCD6 | --raised | Wells, inputs, selected row, lane background |
| rule | #C4C4BC | --rule | Hairlines |
| text | #191A18 | --text | Primary text |
| text-2 | #45463F | --text-2 | Secondary text |
| text-3 | #5F6058 | --text-3 | Engraved labels |
| voice | #A15F00 | --voice | Voice lane strokes, progress fill, focus ring |
| voice-text | #7A4700 | --voice-text | Any text set in the voice color |
| voice-fill | #F2A93B | --voice-fill | Primary button fill (with a 1px #A15F00 edge) |
| removed | #46606F | --removed | Removed-music lane |
| fault | #B8332A | --fault | Errors |
| on-voice | #191A18 | --on-voice | Text on voice-fill |

Contrast: text on ground 14.22, on raised 12.69. text-2 on ground 7.77. text-3 on ground 5.18, on raised 4.62. voice-text on ground 6.26. voice (non-text strokes) on ground 4.12. removed on ground 5.40. fault on ground 4.82. on-voice on voice-fill 8.74.

Amber and steel are close in lightness (1.46 dark, 1.31 light), so they are never the only difference between two things: the lanes are separated in space and each carries its engraved label.

## Typography

### Faces

- **Archivo** (variable, `@fontsource-variable/archivo`, width axis loaded with `wdth.css`): all interface text. Weights 400, 500, 600, 700. Width 100 for reading; width 112 for the wordmark only.
- **Martian Mono** (variable, `@fontsource-variable/martian-mono`, `wdth.css`): every number that changes (timecode, durations, sizes, percentages, ETAs) at width 87.5, weight 450. Tabular by design, so counting digits never jitter.
- **Arabic and other scripts in file names:** the stack falls through to the system: `'Archivo Variable', 'Segoe UI', 'Noto Sans Arabic', system-ui, sans-serif`. File names render with `dir="auto"` inside an isolating element.

Fonts are bundled with the app. Nothing loads from a font CDN.

### Scale

| Token | Face | Size | Line height | Tracking | Weight | Width |
| --- | --- | --- | --- | --- | --- | --- |
| wordmark | Archivo | 18px | 1 | 0.02em | 700 | 112 |
| title | Archivo | 20px | 1.3 | -0.005em | 600 | 100 |
| body | Archivo | 15px | 1.5 | 0 | 400 | 100 |
| body-strong | Archivo | 15px | 1.5 | 0 | 550 | 100 |
| small | Archivo | 13px | 1.45 | 0 | 400 | 100 |
| label | Archivo | 11px | 1.2 | 0.08em, uppercase | 600 | 100 |
| readout | Martian Mono | 13px | 1.3 | 0 | 450 | 87.5 |
| readout-lg | Martian Mono | 20px | 1.2 | -0.01em | 450 | 87.5 |

Nothing is smaller than 11px, and 11px is used only for uppercase labels.

## Spacing

Base unit 4px. Tokens: --s1 4px, --s2 8px, --s3 12px, --s4 16px, --s5 20px, --s6 24px, --s8 32px, --s12 48px, --s16 64px.

- Content column: max 960px, centered, 24px side gutter (16px under 600px wide).
- Queue row: 64px tall, 16px horizontal padding, 12px gap between columns.
- Review panel: 24px padding, 16px between the video, the strip, and the transport.
- Top bar: 56px tall.

## Radius and borders

| Token | Value | Use |
| --- | --- | --- |
| --r-sm | 3px | Buttons, inputs, segmented controls, the switch |
| --r-md | 6px | Rows, wells, panels |
| --r-lg | 10px | The drop well and the settings sheet |

Borders: 1px solid var(--rule). Elevation is flat: surfaces separate by tone, never by drop shadow. The single exception is the settings sheet, which gets `0 12px 32px rgba(0,0,0,0.35)` in dark and `0 12px 32px rgba(25,26,24,0.12)` in light, because it floats over content.

Focus: 2px solid var(--voice), offset 2px, on every focusable element, keyboard focus only (`:focus-visible`).

## Motion

- Easing out (entrances, state settling): `cubic-bezier(0.2, 0, 0, 1)`.
- Easing in (exits): `cubic-bezier(0.4, 0, 1, 1)`.
- Durations: 90ms (switch detent, button press), 160ms (hover and color changes, row insert), 240ms (panel open and close, progress smoothing), 400ms (the strip drawing in once when a job finishes; the only flourish).
- Only `transform` and `opacity` animate. Panel open and close use the View Transitions API where supported and an instant swap where not.
- Progress bars move with `transform: scaleX()` and a 240ms linear transition, so they glide between server updates instead of jumping.
- The Original switch moves in one 90ms step with no overshoot: it is a detent, not a spring.
- Nothing fades in on load. Rows that arrive slide 4px and fade over 160ms.
- `prefers-reduced-motion: reduce` sets every duration to 0 and skips the strip draw-in.

## Components

Every component has default, hover, focus-visible, active, disabled, and where relevant loading, empty, error, and success states. Hover confirms (raise tone or brighten); it never fades the control.

- **Primary button.** Fill --voice (light: --voice-fill with 1px --voice edge), text --on-voice, body-strong, 36px tall, 16px horizontal padding, --r-sm. Hover: brightness 1.06. Active: translateY(1px). Disabled: --raised fill, --text-3 text. Loading: the label stays, a 12px ring spins at its left (static ring under reduced motion).
- **Quiet button.** Transparent, text --text-2, 1px --rule border. Hover: --raised fill, --text. Icon-only quiet buttons are 36 by 36 with an `aria-label` and a tooltip after 500ms.
- **Segmented control** (quality, device): --raised track, selected segment --surface with --text and a 2px --voice underline. Arrow keys move the selection.
- **Select** (output format): native `<select>` styled to match the segmented control. Native because it is accessible and works with every input method.
- **Drop well.** --raised background, 1px --rule border, --r-lg, at least 240px tall when the queue is empty and 88px when it is not (its contents wrap rather than overflow). One line of body text: "Drop audio or video here", a quiet button "Choose files", the link field with a quiet "Add link" button, and a small line listing formats and the link sites. While a drag is over the window, the whole window shows a 2px --voice inset frame and the well text changes to "Release to add". No dashed borders.
- **Text field** (the link field): native `<input type="url">`, 36px tall, --surface fill (it sits on the --raised well), 1px --rule border, --r-sm, 12px horizontal padding, placeholder in --text-2. Hover: border --text-3. Invalid: `aria-invalid`, and the sentence in small --fault text under the field, tied to it with `aria-describedby`.
- **Remove music switch** (link rows, until the job is checked): a native checkbox with `role="switch"`, followed by its label "Remove music" in small --text-2; the accessible name is "Remove music from" plus the file name. Turned off, the label stays the same and the row's link line ends with "download only".
- **Queue row.** --surface, --r-md, 64px. Columns: type glyph (20px), file name (body-strong, middle-truncated, full name in the title attribute), duration (readout), stage (label) above a 4px progress track (--rule) with --voice fill, percentage and ETA (readout), actions (icon buttons). Selected row: --raised. Failed: stage label in --fault with the reason in small text beneath the name; Retry is the row's action. A link row has one more small --text-2 line under the name: "from youtube.com", then the bytes while fetching ("31 MB of 74 MB"), "checked as real video" once ffprobe has read it, and "download only" when music removal is off.
- **The strip.** Two lanes, each 56px tall, on --raised, separated by a 1px --rule center line. Upper lane: the voice kept, drawn as filled min and max peaks in --voice. Lower lane: the music removed, mirrored downward, in --removed. Engraved labels VOICE and REMOVED at the left of each lane. A time ruler above the lanes with tick labels in readout at 10% opacity steps. Playhead: 1px --text line with a 6px square cap on the ruler. Click or drag anywhere to seek; Left and Right move 5 seconds when the strip has focus.
- **Transport.** Play and pause (36px icon button), current time and duration in readout-lg, and the Original switch: a two-position slide switch, 44 by 24, labels CLEAN and ORIGINAL engraved on either side. Holding C, or holding the switch with a pointer, plays the original for as long as it is held; clicking toggles it. The switch is `role="switch"` with `aria-checked`.
- **Status line** (top bar, right): device readout ("CUDA · RTX 3060 Laptop" or "CPU"), library size in readout, settings button.
- **Model download card** (first run): --surface row with the model name, size, a progress track, and two buttons: "Download Best (913 MB)" primary and "Start with Fast (67 MB)" quiet.
- **Settings sheet.** Slides in from the right, 360px wide (full width under 600px), --surface, --r-lg on the leading corners. Contents: quality, device, default output format, data folder path with an Open folder button, storage used and Clear finished jobs.
- **Empty state.** The drop well plus one sentence underneath in --text-2: "Voices stay. Instruments, and most other non-voice sounds, are removed. Your files never leave this computer; a link is fetched from its site, then cleaned here."
- **Errors.** Inline, next to what failed, in --fault, written as what happened plus what to do: "This video has no sound track, so there is nothing to clean." Never a toast for an error.

## Iconography

A small hand-drawn SVG set, inlined as components, no icon library: 20px grid, 1.5px stroke, round caps and joins, `currentColor`. Set: audio file, video file, play, pause, download, cancel (x), retry (circular arrow), delete (bin), settings (three sliders), folder, chevron, check, warning. No other icons are added without adding them here.

## Imagery and texture

None. No photography, no illustration, no noise or grain. The waveforms are the only images.

## Copy

Plain, short, specific. Labels name the thing ("Download", not "Get your file"). Stages are verbs in the present: Checking, Decoding, Separating, Encoding. Numbers come with units. No exclamation marks, no emoji.
