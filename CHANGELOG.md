# Changelog

All notable changes to this project are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and
this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.3.3] — 2026-08-20

### Changed

- **A file in the library is never half-written.** Transfers copied straight to
  the final filename, and `shutil.copy2` truncates the destination to zero the
  moment it opens it — so for the whole duration of a copy, minutes for a film
  over a network share, the library held a file with the right name and the
  wrong contents. An interrupted transfer left it that way. Worse, replacing a
  version already in the library destroyed the existing file as copying began,
  long before there was anything to put in its place: a dropped connection at
  that point loses both. Copying now goes to a temporary name in the same folder
  and the final name is claimed by a rename once the copy is done, which on one
  volume is a single filesystem operation — the name points at the old file or
  the new one, never at something in between. Measured on a deliberately aborted
  copy: 13,000 bytes before, 13,000 bytes after, where the old path left 100.
  The conversion has always worked this way for its own output; the transfer had
  not. Temporary files left by a killed run are cleared on the next transfer.

## [1.3.2] — 2026-08-19

### Fixed

- **The details page showed fewer files as running than the queue did.** With
  three parallel tasks the queue listed three, the details page two. Two causes:
  a file only switched to *Processing* on its first progress report from FFmpeg,
  so it sat on *Waiting* while its encoder was already starting; and the details
  page was rebuilt only when a file finished, leaving it on the state from the
  last completed one. It now follows the start of each file — once per file,
  not on every progress report, where three files reporting twice a second
  would mean six full rebuilds per second.
- **The details page showed its status untranslated.** It wrote the raw value,
  so an English interface listed *Waiting* in the queue and *Wartend* beside it
  in the details.

## [1.3.1] — 2026-08-18

### Fixed

- **After a run in which everything had already been moved, the application
  stayed on the conversion page and left the library list stale.** Switching to
  the library and re-reading it hangs off the completion of the closing
  transfer — and since 1.2.4 there is no closing transfer when the run has
  already moved everything, so nothing completed and nothing happened. The
  transfer had run, just earlier; the end of it now looks the same either way,
  including the notification. Until 1.2.3 this was masked by the duplicate
  transfer: the redundant second pass was what triggered the page switch.

## [1.3.0] — 2026-08-18

Two things you could not do before: convert files that used to fail, and know
what a setting costs before the run rather than after.

### Added

- **4:4:4 and 4:2:2 sources convert to AV1 instead of failing.** NVENC's AV1
  encoder accepts only 4:2:0 and otherwise reports `No capable devices found`,
  which reads like a broken GPU. Amboss now converts the chroma subsampling —
  and only that. The bit depth is kept, so a 10-bit source stays 10-bit and HDR
  stays HDR; the obvious one-line fix, a blanket `-pix_fmt yuv420p`, would have
  flattened every HDR source to 8 bit and produced exactly the banding one
  notices first. Formats above 10 bit land at 10, which is more than any
  playback device outputs. H.265 and H.264 accept 4:4:4 directly and are left
  untouched — a conversion nobody needs is pure loss. A format that is neither
  known nor 4:2:0 is not touched either: it fails visibly rather than being
  quietly degraded. Every conversion is noted in the log.
- **A report before the run of what the chosen settings will lose.** Sources are
  deleted once the output is verified, so the dangerous failure is not the crash
  but the silent loss — a file that converts, passes duration and stream checks,
  and is still worse than the original that then disappears. Before starting,
  the selected codec and container are compared against what the files actually
  contain: lossless audio that MP4 refuses outright, image-based and positioned
  subtitles, chroma finer than AV1 takes, and HDR against H.264, which can only
  do 8 bit and would hand back washed-out SDR without a single warning.

  Each finding can be fixed from the dialog, and the fix applies **only to the
  affected files** — a season with three episodes carrying PGS subtitles moves
  those to MKV and leaves the rest of the queue as configured. For series the
  switch covers the whole season, so a season folder is not left half MP4 and
  half MKV; for movies it is per file. Findings without a remedy, such as Dolby
  Vision, are stated rather than offered. The dialog appears only when there is
  something to report, and can be silenced per combination of codec and
  container — a warning that becomes a clicking exercise stops working on the
  day it matters.

### Fixed

- **A library transfer with nothing to transfer was reported as successful.**
  The completeness check is source-relative — it counts whether every source
  file arrived at the target — and with zero source files that is trivially
  true: nothing copied out of nothing expected, and the verification finds
  nothing to object to because there is nothing to check. A folder that had
  vanished or could not be read therefore showed up as *Finished*, and with
  *delete local folders* selected it was cleaned up as well. An empty or
  unreadable source folder is now an error, and no target folder is created for
  it. Found by running the real transfer code against real files rather than a
  stand-in.
- **The graphics-card error message no longer points at 4:4:4 chroma.** That
  case is now handled, so the old wording sent people down a dead end.

## [1.2.4] — 2026-08-18

### Fixed

- **A finished item could be reported as failed although it had arrived
  intact.** Since 1.2.2 folders are moved to the library while the rest is
  still converting, but the closing transfer knew nothing about that: when the
  conversion ended it rescanned the output folder, found an item the first
  transfer was still working on, and started moving it a second time. One of
  the two won; the other found the folder gone from under it and reported an
  error — on a file that was complete in the library. The closing transfer now
  waits for the one running alongside the conversion and skips whatever it
  already moved, which stays visible in the list as finished.
- **A configured shutdown could fail to happen** for the same reason. Once
  everything had been moved during the run there was nothing left for the
  closing transfer, which returned before reaching the shutdown it was supposed
  to trigger. The machine then stayed on all night.

## [1.2.3] — 2026-08-17

### Added

- **Amboss says when a new version has been published.** Until now a release
  reached nobody who was not watching the repository, which makes a fix worth
  little. At startup Amboss asks GitHub what has been released and, if
  something newer exists, shows what changed — in *every* version since the
  installed one, not only the latest. Going from 1.2.3 to 1.4.0 means 1.2.4 and
  1.3.0 were never seen, and the entry that matters may well be in one of them;
  the list scrolls, the button always leads to the newest version.

  Nothing is downloaded and nothing is replaced. Windows will not let a running
  executable overwrite itself, so a self-update would have to swap the file
  during the next start — precisely the behaviour antivirus software treats as
  malicious in an unsigned program. For a tool that deletes source files,
  predictability is worth more than convenience.

  The request is a plain unauthenticated GET to `api.github.com`; nothing
  accompanies it — no identifier, no machine details, no usage data. A single
  version can be dismissed for good, the check can be switched off entirely,
  and *Check now* under Settings runs it on demand, ignoring an earlier
  dismissal. It is skipped on first run and fails silently without a
  connection.

### Fixed

- **The transfer progress bar could sit at a partial value after everything had
  been moved.** Folders sent during the run were not connected to it, so it
  showed whatever an earlier transfer had left behind — and a bar stuck at 30 %
  reads as a stalled job even when the work is done. It now follows both kinds
  of transfer and settles at 100 % once nothing is left to move.

## [1.2.2] — 2026-08-16

Nothing new to operate — the same settings do the same things. What changed is
when the work happens and what is left behind when part of it fails.

### Changed

- **Finished items move to the library while the rest is still converting.**
  The share previously sat idle for the whole batch and then worked through
  everything at once; over a run of several hours the first movie was done long
  before the last episode started. A folder is sent as soon as no queued file
  still targets it, which also covers interleaved queues — series A, series B,
  series A again. Requires *Move into library* to be selected.
- **A source is deleted once its own output is verified**, rather than only
  after the entire batch succeeded. Out of a season of 24 episodes where one
  fails, 23 sources are now cleared instead of none. Both checks still have to
  pass first, and an interrupted run still deletes nothing.
- **Sources that failed are set aside** in `_InProgress/_Failed`, so what
  remains in the watched folder is exactly what needs attention. A fresh scan
  finds only those.
- **A second instance no longer reaches for files the first one is working on.**
  A running conversion marks its folder; another scan skips those files while
  the mark is current and the process is alive. Files stranded by a crash become
  visible again, and the failed-files folder is always visible.
- **The log is English regardless of the interface language**, and no longer
  uses emoji. It is a technical record — read when something went wrong, often
  pasted into a search or handed to someone else — so one language serves it
  better than two. The interface itself remains available in both. Entries that
  carry a judgement are marked `OK:`, `ERROR:` or `WARNING:`, which can be
  searched for and render in any font.

### Added

- **A report at the end of a run that had failures**, naming each file, why it
  failed and where it now is. Previously the message listed filenames and
  pointed at the log, which meant searching several hundred lines to find out
  why episode 22 of 24 did not make it.

### Fixed

- **Confirming the media types reset every target to MP4.** The dialog
  recalculates target paths afterwards and did so without the selected
  container, so choosing MKV together with automatic library transfer silently
  produced `.mp4` paths.

## [1.2.1] — 2026-08-15

### Fixed

- **The quality slider's handle stayed put when the codec changed.** The filled
  bar is redrawn from value and maximum on every repaint and moved immediately,
  but the handle is only repositioned on a value change — switching codec
  changes the maximum, not the value, so the two drifted apart by up to 56
  pixels. The handle now follows a range change as well.
- **The per-type sliders under Advanced showed the wrong scale.** They read the
  main codec rather than their own, so selecting H.265 there displayed AV1's
  scale of 63 next to it.
- **Their handle could sit outside the slider entirely.** A slider laid out
  while its panel is still hidden is positioned at the default width and never
  corrected afterwards — measured at 244 px inside a 180 px slider.

## [1.2.0] — 2026-08-15

### Added

- **Formats other than MP4 are read.** `.mkv`, `.avi`, `.ts`, `.mov`, `.m4v`,
  `.wmv`, `.flv`, `.webm`, `.mpg`, `.mpeg` and `.m2ts` are now found by the
  scan. Previously only `.mp4` was, so a folder of MKV releases — which is what
  most series and animation downloads are — reported nothing found, with no
  indication that the extension was the reason.
- **H.265 (HEVC) is available as a codec.** It sits between AV1 and H.264:
  smaller files than H.264, and playable on devices that predate AV1. Written
  to MP4 it is tagged `hvc1` rather than FFmpeg's default `hev1` — without that,
  Apple devices refuse to play the file even though it is perfectly valid. It
  also converts 4:4:4 sources, which the AV1 encoder rejects.
- **MKV can be chosen as the output container.** MP4 remains the default
  because it plays on the widest range of devices. MKV takes what MP4 cannot:
  lossless TrueHD and DTS-HD MA tracks, image-based subtitles (PGS, VobSub) that
  otherwise have to be dropped, and ASS subtitles with their positioning intact
  instead of flattened to `mov_text`.

### Changed

- **The quality slider follows the codec.** AV1 rates quality on a scale to 63,
  H.265 and H.264 only to 51, so the same number sat at a different point
  depending on the codec — and the stronger AV1 compression was unreachable
  because the slider stopped at 51 for everything. It now ends where the codec
  ends, and the label names the scale (`CQ 37/63` rather than `CQ 37`).
  Switching from a high AV1 value to H.265 lowers it to that codec's maximum,
  visibly rather than behind the scenes.
- A card that cannot encode AV1 is now pointed at H.265 rather than H.264. Both
  work, but H.265 produces considerably smaller files.
- Filename detection no longer requires a `.mp4` ending, so an episode named
  identically as `.mkv` is recognised the same way.
- Changing the container recalculates the targets of files already scanned,
  rather than leaving paths on screen that would not be produced.

## [1.1.1] — 2026-08-14

### Added

- **The changelog can be read inside the application**, under Settings. It is
  the same file that ships with the source, so there is one text rather than a
  second one that drifts out of date.

### Fixed

- **Scanning now shows that it is working.** Moving the scan off the interface
  thread stopped the freeze but left nothing on screen: the expensive step —
  reading the season-folder convention from the library — reports once and then
  works silently for several seconds, so the status text sat still and looked
  no different from a hang. A spinner now runs alongside it, which animates
  regardless of whether progress is being reported, next to the name of the
  file being examined.

## [1.1.0] — 2026-08-13

### Added

- **Sleep is suppressed while work is in progress.** A batch commonly runs for
  hours and unattended. If the machine went to sleep, encoding stopped until
  someone woke it, and a configured shutdown never fired. The display is
  deliberately left alone and may still switch off.
- **Output is verified against the number of streams**, not only against
  duration. A file of the correct length can still be missing a second audio
  track, and neither duration nor size reveals it. Since sources are deleted
  after a clean run, that was the failure with the highest cost.

### Changed

- **Scanning no longer blocks the interface.** It now runs off the interface
  thread and reports progress per file. Previously the window froze for the
  duration — on a network library that meant roughly ten seconds without any
  feedback, because reading the season-folder convention alone lists up to
  sixty show folders per category. Clearing stale temporary files was moved to
  after the scan rather than in front of it.

### Fixed

- The library list is refreshed once a transfer completes. Items that had
  already been moved stayed on screen until the next manual scan.

## [1.0.2] — 2026-08-12

### Fixed

- **The category column no longer truncates its entries.** Its width was fixed,
  which fit the German labels but cut the English ones off mid-word. The column
  is now sized from the rendered width of the actual category names, so it holds
  for either language and for any label added later. This affects the media type
  confirmation dialog and the library table.

### Documentation

- Added a section on what survives conversion and what does not — lossless
  Blu-ray audio, Dolby Vision, subtitle positioning and 4:4:4 sources — each
  verified by round-tripping a test file through the actual conversion command
  rather than reasoned from the format specifications.
- Added a list of planned work: H.265, MKV as an output container, software
  encoding, and AMD/Intel support.
- Documented loudness normalisation and HDR passthrough, neither of which had
  been mentioned despite being present since the first release.

## [1.0.1] — 2026-08-12

### Added

- **FFmpeg is fetched on request when it is missing.** Installing FFmpeg by hand
  and putting it on `PATH` was the step most first-time users stumbled over.
  Amboss now offers to download it, naming the source, the size and the target
  folder before anything is transferred, and verifies the archive against the
  publisher's SHA-256 checksum before extracting. Nothing is installed system
  wide; the files live beside the configuration and deleting that folder undoes
  it. Declining leaves the previous behaviour untouched.
- **The detected graphics card is shown** in the system panel at the bottom of
  the sidebar, with the full model name on hover. Previously a message about
  unsupported hardware gave no way to see what had actually been found.
- **Graphics card detection on startup.** Amboss now identifies the installed
  GPU and reports unsupported hardware directly, naming the card it found
  instead of failing later with an FFmpeg error. A card that cannot encode AV1
  is distinguished from one that is not supported at all: NVIDIA cards below the
  RTX 4000 series are told that H.264 remains available to them.
- **Encoder unit hint next to the concurrent task count.** The number of
  concurrent conversions that a card can usefully sustain is bounded by its
  NVENC units, a figure no driver interface reports. Amboss now shows it and
  points out when the configured value exceeds it. The setting is deliberately
  not capped — measured throughput does keep rising past that point, just
  barely, and that trade-off belongs to the user.
- **Encoder support matrix in the documentation**, covering NVIDIA, AMD, Intel
  and software encoding, so the supported scope is visible at a glance.

### Changed

- The concurrent task limit was raised from 5 to 8, which the new hint makes
  safe to expose.

### Removed

- The unused official AV1 logo asset, which was still being packaged into the
  executable despite no longer being referenced by any code path.

## [1.0.0] — 2026-08-12

First release.

Batch conversion to AV1 or H.264 through NVIDIA NVENC, with filename-based
detection of series, animated series and movies, and automatic filing into a
media library. Every audio track and text subtitle is preserved, source files
are removed only after a verified clean run, and library transfers are compared
byte for byte. Interface in English and German.
