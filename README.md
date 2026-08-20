<div align="center">

<img src="logo.png" width="104" alt="">

# Amboss

**Batch video converter for Windows — AV1, H.265 and H.264 via NVIDIA NVENC, with
automatic media detection and library filing.**

[Download](../../releases) · [Changelog](CHANGELOG.md) · [License](LICENSE)

<img src="docs/screenshot.png" width="900" alt="">

</div>

---

Amboss re-encodes a folder of video files to AV1, H.265 or H.264 using NVIDIA's
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

**A source file is deleted only once its own output has been verified.** Every
output is checked twice: against the source duration, because a truncated encode
produces a playable file of the wrong length that a size check does not catch,
and against the number of streams, because a file of the correct length can
still be missing a second audio track — that failure leaves no trace in duration
or size, and it is the one that would cost the most if the source were already
gone. A file that fails either check is never queued for deletion.

**Sources that failed are set aside** in `_InProgress/_Failed`, and the run ends
with a report naming each one, why it failed and where it now is. Out of a
season of 24 episodes where one fails, exactly one file remains and a fresh scan
finds only that one. An interrupted run deletes nothing at all, since what was
mid-flight cannot be established.

**The computer is kept awake while work is in progress.** A batch easily runs
for hours, usually overnight. Sleep is suppressed for the duration of encoding
and of library transfers, and released again afterwards. The display is not kept
awake — the screen may switch off as usual.

**Library uploads are verified byte-for-byte.** Every file is compared against
its counterpart before local copies are deleted.

**A file in the library is never half-written.** Copying goes to a temporary
name in the destination folder and the final name is only claimed once the copy
is complete — a rename, which on one volume is a single filesystem operation.
Interrupt a transfer and the library holds either the finished new file or the
untouched old one, never something in between. This matters most when replacing
a version you already have: writing straight to the final name destroys the
existing file the moment copying starts, long before there is anything to
replace it with. Leftover temporary files from a killed run are cleared on the
next transfer.

**Finished items are moved while the rest is still converting.** With automatic
filing selected, a folder is sent as soon as no file left in the queue targets
it — a movie right after its own conversion, a series once its last episode is
done, regardless of the order they were queued in. Otherwise the network share
would sit idle for hours and then have to move everything at once. A folder
containing a failed file is held back and goes with the transfer at the end,
rather than putting an incomplete season into the library unannounced.

**Episode information is written into the file itself.** Alongside renaming,
each output carries `title`, `show`, `season_number` and `episode_sort` as
metadata; movies carry `title`. Media servers read these tags rather than
guessing from the path, so a file identifies itself correctly even after it is
moved or renamed by something else.

**Loudness can be normalised to EBU R128** (−23 LUFS, true peak −2 dBTP), which
levels out the volume differences between releases from different sources. It is
optional and off by default, since it requires re-encoding the audio rather than
copying it.

**HDR is preserved.** Bit depth, colour primaries, transfer characteristics and
matrix coefficients carry through to the output, so an HDR10 source stays HDR10
rather than arriving washed out.

**Sources are moved to `_InProgress` when a run starts**, leaving the watched
folder free for new downloads while encoding is under way. Scanning alone never
moves or deletes anything. A second instance scanning the same folder skips
whatever the first one is working on, so the two never reach for the same file;
files left behind by a crash become visible again once that instance is gone.

**What a setting will cost is shown before the run, not after.** Amboss deletes
source files once the output is verified, which makes the silent loss the
dangerous failure: a file that converts, passes both checks and is nevertheless
worse than the original that then disappears. Duration and stream count are
right in that case — only the picture is not, and that shows up when you watch
it, long after the source is gone. So before a run starts, the selected codec and
container are compared against what the files actually contain, and anything that
would be lost is named: lossless audio that MP4 cannot carry, image-based or
positioned subtitles, chroma finer than AV1 accepts, and HDR against H.264, which
can only do 8 bit.

Each finding can be fixed from the dialog, and the fix applies **only to the
affected files** — a season with three episodes carrying PGS subtitles switches
those to MKV and leaves the rest of the queue alone. For series the switch covers
the whole season, so a season folder does not end up half MP4 and half MKV; for
movies it is per file. Findings without a remedy, such as Dolby Vision, are stated
rather than offered. The dialog appears only when there is something to report and
can be silenced per combination of codec and container.

**New versions are announced, never installed.** At startup Amboss asks GitHub
whether anything newer has been published and, if so, shows what changed in
every version since the installed one — going from 1.2.3 to 1.4.0 means 1.2.4
and 1.3.0 were never seen, and the fix that matters may be in one of them. The
button opens the releases page in a browser; the file is downloaded and put in
place by hand. Nothing is fetched automatically and the running executable is
never replaced underneath itself. A single version can be dismissed for good, or
the check turned off entirely under Settings. See
[Update check](#update-check) for what is transmitted.

Additionally: separate quality presets for animation and live action, remaining
time for the whole batch derived from measured throughput, detection of duplicate
downloads (`File.mp4` alongside `File (1).mp4`), a Windows notification on
completion, and an optional shutdown afterwards.

## What survives the conversion

Verified by round-tripping test files through the actual conversion command and
inspecting the result.

| | Result |
|---|---|
| HDR10 — bit depth, primaries, transfer, matrix | Preserved |
| Bit depth of 4:4:4 and 4:2:2 sources under AV1 | Preserved; only the chroma subsampling is reduced |
| Frame rates up to 144 fps, and 4K | Preserved exactly |
| Multiple audio tracks — AC-3, E-AC-3, DTS, FLAC, AAC | Preserved, all channels |
| SubRip subtitles | Preserved, including basic styling |
| ASS/SSA subtitles | Text, colour, size and weight preserved |
| Chapter marks and stream language tags | Preserved |
| Series, season and episode | Written into the output as metadata |

## Limitations

These are the cases where something is lost or the file will not convert, and
what causes each one — the MP4 container, the limits of NVENC, or a decision
made here.

**TrueHD audio requires MKV output.** TrueHD — the carrier for Dolby Atmos on
Blu-ray — can technically be placed in MP4, but FFmpeg still classes that
combination as experimental and refuses it (verified on FFmpeg 7.1.1). Choosing
MKV as the container solves it: the track is carried through untouched. With
MP4 selected, such a file fails rather than losing the track silently — the
output is discarded and the source left alone. Web releases are unaffected
either way, since they carry Atmos inside E-AC-3, which MP4 handles normally.

**Dolby Vision metadata is expected to be lost.** NVENC does not carry it
through a re-encode. Where a source also has an HDR10 base layer, that base
should survive and the picture stay HDR; a source without one is unlikely to
come out looking right. This is the one entry here that could not be tested —
see below.

**ASS subtitle positioning is lost in MP4.** Converting to `mov_text` keeps the
text and its basic appearance but drops absolute positioning and karaoke timing,
so typeset signs in fansubs appear as plain subtitle lines. MKV keeps the tracks
as they are.

**Bitmap subtitles are dropped in MP4.** PGS and VobSub are images, not text,
and MP4 cannot store them; they are skipped so the encode still succeeds. MKV
carries them through.

**Chroma is reduced to 4:2:0 for AV1 when the source is not.** NVENC's AV1
encoder accepts only 4:2:0 and otherwise reports `No capable devices found`, a
message that reads like a missing or broken GPU but means only that this
combination is unsupported. Rather than failing, Amboss converts the chroma
subsampling — and only that: the bit depth is kept, so a 10-bit source stays
10-bit and HDR stays HDR. A 4:4:4 or 4:2:2 source therefore loses colour
resolution, which is a real loss, but a far smaller one than the 8-bit flattening
a blanket conversion would cause. It is noted in the log whenever it happens.
H.265 and H.264 accept 4:4:4 directly and are left untouched. Ordinary releases
are 4:2:0 and unaffected either way. A format that is neither listed nor 4:2:0 is
not touched at all — it fails visibly instead of being quietly degraded.

**Encoding is NVIDIA-only** — see the table below.

### Not verified

Everything above was checked against real files. The following could not be, and
is stated as expectation rather than fact. Reports from anyone able to test these
are welcome.

| | Why it is untested |
|---|---|
| DTS-HD Master Audio | FFmpeg cannot produce a lossless DTS track, so no test file could be built. Core DTS is verified and converts normally. |
| Dolby Vision | Building a stream with a genuine Dolby Vision layer is not possible with the tools at hand. |
| Behaviour on AMD and Intel GPUs | No such hardware available — which is also why those encoders are not implemented. |

## Planned

Nothing here is implemented yet. The list is ordered by what would remove the
most friction, not by what is most interesting to build.

| | Why |
|---|---|
| Software encoding (SVT-AV1) | Makes the application usable without a suitable GPU |
| AMD (AMF) and Intel (Quick Sync) | Hardware encoding for the remaining vendors — see the note on why this is last |

The vendor encoders are deliberately last. Amboss verifies output against the
source duration, not against picture quality, so an encoder that runs but
produces poor results would report success and the sources would be deleted.
That cannot be ruled out without the hardware to test on.

## Requirements

- Windows 10 or 11
- An NVIDIA GPU with NVENC — see below
- FFmpeg and FFprobe. If they are not on `PATH`, Amboss offers to download them
  on first launch and keeps them in its own folder, leaving the system untouched.
  The archive is checked against the publisher's SHA-256 before anything is
  extracted, and nothing is downloaded without asking first.

Input may be `.mp4`, `.mkv`, `.avi`, `.ts`, `.mov`, `.m4v`, `.wmv`, `.flv`,
`.webm`, `.mpg`, `.mpeg` or `.m2ts`. Output is MP4 by default, with MKV
selectable — MKV carries lossless audio and image-based subtitles that MP4
cannot hold. See [Limitations](#limitations).

### Encoder support

The table describes what Amboss implements, which is narrower than what the
hardware can do.

| Encoder | AV1 | H.265 | H.264 |
|---|:--:|:--:|:--:|
| **NVIDIA** — NVENC | ✔ | ✔ | ✔ |
| **AMD** — AMF | ✘ | ✘ | ✘ |
| **Intel** — Quick Sync | ✘ | ✘ | ✘ |
| **CPU** — software encoding | ✘ | ✘ | ✘ |

✔ available · ✘ not implemented

AV1 requires a GeForce RTX 4000 series card or newer and gives the smallest
files. H.265 is the middle ground for devices that predate AV1, and H.264 plays
on practically anything. H.265 written to MP4 is tagged `hvc1` rather than
FFmpeg's default `hev1`, without which Apple devices refuse to play the file.

Quality is set as a CQ value, where lower means better. The scales differ by
codec — AV1 runs to 63, H.265 and H.264 to 51 — so the slider ends where the
selected codec ends and the label names the scale, as `CQ 37/63`. The same
number therefore does not mean the same thing across codecs. Speed presets
(`p1` fastest to `p7` best) are identical for all three.

AMD and Intel are not simply untested. Amboss passes NVENC-specific parameters
throughout — `-cq` for quality, `-preset p1…p7` for speed — and FFmpeg rejects
those for other encoders while still parsing options, long before a GPU is
involved. Supporting them means mapping every parameter per encoder, which is
planned rather than pending, alongside software encoding as a fallback for
machines without a suitable GPU.

Worth separating, because it is a common source of confusion: playing AV1 back
and producing it are two different hardware capabilities. Nearly every recent
GPU, integrated graphics included, decodes AV1; far fewer can encode it. An
RTX 3080 plays AV1 without effort but cannot create it.

Amboss verifies the selected encoder against FFmpeg on startup and reports a
missing one rather than failing part-way through a batch.

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
next start. A light and a dark theme are available and switch immediately.

The changelog is readable from inside the application, under Settings.

One option is deliberately not persisted: *shut down PC when finished* resets on
every launch, so a forgotten checkbox cannot power off the machine during a later
session.

### Update check

Amboss makes exactly one kind of network request on its own: at startup it asks
`api.github.com` for this repository's published releases, to find out whether
anything newer than the running version exists. It is a plain unauthenticated
GET; nothing is sent along with it — no identifier, no machine details, no usage
data — and nothing is written anywhere but the two settings below. Turning the
check off means no request is made at all.

| Setting | Meaning |
|---|---|
| *Check for new versions at startup* | On by default. Off means Amboss never contacts the network by itself. |
| *Stop reminding me about X* | Suppresses one particular version. A later, higher version is reported again. |

The check is skipped on first run, fails silently when there is no connection,
and never blocks the interface. *Check now* under Settings runs it on demand and
ignores a previously dismissed version — an explicit question deserves the real
answer.

Downloading and replacing `Amboss.exe` remains a manual step. Windows will not
let a running executable overwrite itself, so a self-update would have to swap
the file during the next start, which is exactly the behaviour antivirus
software treats as malicious in an unsigned program. For a tool that deletes
source files, being predictable is worth more than being convenient.

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
| `update_check.py` | Asks GitHub whether a newer version exists |
| `i18n.py` | Interface translations |
| `ui/` | User interface |

## License

Licensed under the GNU General Public License v3.0 — see [LICENSE](LICENSE).
Amboss links PyQt5 and PyQt-Fluent-Widgets, both distributed under the GPLv3,
which applies to the combined work.

AV1™ is a trademark of the Alliance for Open Media. Amboss implements the AV1
specification and is not affiliated with, endorsed by, or certified by the
Alliance for Open Media.
