<div align="center">

<img src="logo.png" width="104" alt="">

# Amboss

**Batch video converter for Windows — AV1 and H.264 via NVIDIA NVENC, with
automatic media detection and library filing.**

[Download](../../releases) · [License](LICENSE)

<img src="docs/screenshot.png" width="900" alt="">

</div>

---

Amboss re-encodes a folder of video files to AV1 or H.264 using NVIDIA's hardware
encoder, identifies each file from its name, renames it to a consistent scheme,
and moves the result into the matching folder of a media library.

It is built for unattended batch runs. Select a folder, start the queue, and the
application handles detection, encoding, verification and filing without further
input.

## Detection and filing

Each file is classified during the scan, based on its filename:

| Filename | Detected as |
|---|---|
| `Episode 3 Staffel 1 von Bleach.mp4` | Animated series, season 1, episode 3 |
| `The Bear S02E04 ... .mp4` | Series, season 2, episode 4 |
| `Spirited Away.mp4` | Movie |

Categories are defined by their target folders: point *Movies* at
`\\NAS\Media\Movies`, *Series* at `D:\TV`, and so on. A category with no folder
assigned is treated as non-existent, and anything detected as belonging to it is
filed under the closest category that does exist. A library without a separate
animated-movies folder therefore receives animated movies alongside regular ones,
rather than gaining a directory it was never meant to have.

**Amboss never invents folder names.** The staging directory mirrors the target
folders you configured, and season directories follow whatever convention already
exists in your library — `Season 02`, `Staffel 2`, `シーズン 1`, or plain `2`. The
convention is read from your existing shows, so new episodes land next to the old
ones instead of in a parallel directory. With an empty library, season folders are
numbered, which is the only form that is not wrong in some language.

On first launch, Amboss asks once which categories your library actually has and
where they live. Everything it asks for can be changed later under Settings.

<img src="docs/setup.png" width="760" alt="">

## Behaviour worth knowing about

**All audio tracks and text subtitles are preserved.** FFmpeg's default stream
selection keeps only one track per type; a release with both a dubbed and an
original audio track silently loses one. Amboss maps every audio stream
explicitly and converts text-based subtitles to `mov_text`. Bitmap subtitle
formats that MP4 cannot carry are skipped rather than failing the encode.

**Source files are deleted only after a completely clean run.** Deletion is
deferred until every file in the batch has finished, and each output is verified
against the source duration first. A truncated encode produces a playable file of
the wrong length, which a size check does not catch. If any file fails, no source
is removed.

**Library uploads are verified byte-for-byte.** Every file is compared against
its counterpart before local copies are deleted.

**Sources are moved to `_InProgress` when a run starts**, leaving the watched
folder free for new downloads while encoding is under way. Scanning alone never
moves or deletes anything.

Additionally: separate quality presets for animation and live action, remaining
time for the whole batch derived from measured throughput, detection of duplicate
downloads (`File.mp4` alongside `File (1).mp4`), a Windows notification on
completion, and an optional shutdown afterwards.

## Requirements

- Windows 10 or 11
- An NVIDIA GPU with NVENC — see below
- FFmpeg and FFprobe available on `PATH`

### Hardware support

**Encoding requires NVIDIA hardware.** Amboss drives NVENC through FFmpeg and
passes NVENC-specific parameters throughout. AMD (AMF) and Intel (Quick Sync)
are not merely untested — they are not implemented, and FFmpeg rejects the
current parameters before it ever reaches the GPU. Support for them, and for
CPU-based encoding as a universal fallback, may be added later.

| Codec | Requirement |
|---|---|
| AV1 | GeForce RTX 4000 series or newer |
| H.264 | Practically any NVIDIA GPU of the past decade |

Worth separating, because it is a common source of confusion: playing AV1 back
and producing it are two different hardware capabilities. Nearly every recent
GPU — integrated graphics included — decodes AV1; far fewer can encode it. An
RTX 3080 plays AV1 without effort but cannot create it.

Amboss checks the selected encoder against FFmpeg on startup and reports a
missing one rather than failing mid-run.

## Installation

Download `Amboss.exe` from [Releases](../../releases) and run it. There is no
installer and nothing is written outside `%APPDATA%\Amboss`.

Running from source:

```
pip install -r requirements.txt
python main.py
```

Building the executable:

```
pyinstaller amboss.spec
```

## Configuration

Settings are stored in `%APPDATA%\Amboss\config.json`, together with `app.log`
and `crash.log`.

The interface is available in English and German; the language follows the system
locale by default and can be changed under Settings. A change takes effect on the
next start.

One option is deliberately not persisted: *shut down PC when finished* resets on
every launch, so a forgotten checkbox cannot power off the machine during a later
session.

## Project layout

| File | Purpose |
|---|---|
| `main.py` | Entry point, language setup, crash logging |
| `models.py` | Data types, constants, category folding |
| `pattern_matcher.py` | Filename-based media detection |
| `path_generator.py` | Target path construction and collision handling |
| `duplicate_detector.py` | Duplicate download detection |
| `inprogress_mover.py` | Moving sources to `_InProgress` |
| `merge_detector.py` | Detection of truncated folder names |
| `library_layout.py` | Reads folder conventions from the existing library |
| `ffmpeg_processor.py` | FFmpeg and FFprobe invocation |
| `workers.py` | Conversion and upload, off the UI thread |
| `i18n.py` | Interface translations |
| `ui/` | User interface |

## License

Licensed under the GNU General Public License v3.0 — see [LICENSE](LICENSE).
Amboss links PyQt5 and PyQt-Fluent-Widgets, both distributed under the GPLv3,
which applies to the combined work.

AV1™ is a trademark of the Alliance for Open Media. Amboss implements the AV1
specification and is not affiliated with, endorsed by, or certified by the
Alliance for Open Media.
