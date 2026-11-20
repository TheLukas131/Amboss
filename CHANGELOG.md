# Changelog

All notable changes to this project are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and
this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **A file that runs alone uses every encoder unit of the card.** A conversion
  occupies one NVENC unit; on a card with three, a single film left two of
  them idle. NVENC can divide each frame into horizontal strips and let the
  units work on them at once (split frame encoding), and Amboss now asks for
  that whenever a file has the card to itself — a single file, or any run with
  one concurrent task. With several files running side by side nothing
  changes: each already has a unit of its own, and that is the better state,
  because splitting costs a little compression at the strip boundaries and
  running in parallel costs nothing.

  For AV1 and H.265; H.264 cannot do it. Requires FFmpeg 7.1 or newer — an
  older one is detected and simply not given the option. Should the driver or
  card refuse, the file is converted the ordinary way and the rest of the run
  does not try again. The decision is made when a file starts and holds for
  that file: the last one left over while the others finish runs unsplit to
  the end. Can be switched off under *Advanced*. **Not measured on a real
  card** — the decision, the command and the fallback are tested, the gain in
  speed is not.

- **The queue shows a season as one row.** Twenty-four episodes were
  twenty-four near-identical rows among which the one film got lost. Episodes
  of a season now sit under a shared row with their combined progress, size and
  target folder; a click opens or closes it. Seasons start closed once the
  queue is longer than twelve files.
- **A running file shows numbers, a finished one its saving.** Percentage and
  time remaining under the bar while it encodes, the latter from the speed
  FFmpeg itself reports; afterwards the size before and after — `2.6 GB →
  655 MB (−75 %)` — in a column of its own.

- **What was done stays written in the window.** The end of a run was
  announced by a Windows notification and a toast that vanished after four
  seconds. A run usually ends while nobody is watching; whoever came back and
  no longer found the notification had only the log. The result now stands at
  the top of the page, with the time, until it is closed or a new run starts —
  the conversion and the transfer each on a line of their own, on the
  conversion page and in the library alike. A stopped run says *stopped*
  rather than *finished*. The same result also comes up as a dialog in front
  of the window, once everything is through — after the transfer if one was
  selected, not after the conversion before it — and waits there to be
  confirmed. It is left out where another dialog already says it: the
  shutdown countdown, and the failure report after a run without transfer.
- **The filters count.** *Waiting 4*, *Failed 1* — how many files each would
  show, without having to click through them.

### Changed

- **The conversion page shows the queue, not its own controls.** The table has
  three columns instead of seven: file, state, size. State and progress are
  one cell — a bar with percentage and time remaining while a file runs, the
  word otherwise — where the word *Processing* used to sit next to a bar saying
  the same. Type and target moved to the details of a file. The remove button
  appears in the row under the mouse only. Source, target and encoder settings
  fold into one line once there is a queue and open again with *Change*. The
  page heading is gone, the footer shows only the buttons that can do
  something, and the filters appear only when there is something to filter.
- **Details moved from their own page into the queue.** They were a second list
  of the same files on another page, to be found again and opened there. A
  click on a row now shows codec, resolution, bitrate, audio and subtitle
  tracks, duration and size before and after right beneath the queue; a second
  click closes it. The *Details* page is gone.
- **The footer says how far, how many and how long.** Progress bar, count,
  percentage and time remaining on one line, and the balance in one sentence
  below — `10 files · 3 converted: 22.0 GB → 5.5 GB (−75 %) · 1 failed`.
  Before, it was six fields, two of which read *still running…* for the whole
  run: the saving compared the entire queue against the files finished so far,
  which gave absurd figures and was therefore hidden. It now compares what was
  converted with itself and is right at any moment.
- **Source and output folder take one line less each**, which goes to the
  queue.
- **The target column shows the path relative to the output folder**, on one
  line. Every row used to begin with the same stretch of path and wrapped
  because of it, with the part that differs at the end of the second line. The
  full path is in the tooltip. In a narrow window the column gives way to the
  file name.

- **A file is read by ffprobe once instead of five times.** Each conversion
  started four ffprobe processes around the encode — subtitle codecs, stream
  count, then duration and stream count of the output — and the interface
  started a fifth on its own thread to fill the details page, which held the
  window for the length of that call every time a file finished. The scan had
  already read the source; its result is now used, and the output is read once
  for both checks and for the details. Measured: 5 process starts per file
  before, 1 after. The checks themselves are unchanged — a lost audio track and
  a truncated output are rejected exactly as before, and where the scan could
  not read a file, the source is asked again rather than trusted to have no
  streams.
- **Startup waits for fewer programs, and for them side by side.** Before the
  window appeared, five processes ran one after the other: `ffmpeg -version`,
  `ffprobe -version`, `ffmpeg -version` a second time, the encoder list and
  `nvidia-smi`. The repeated call is gone and the rest overlap. Starting a
  conversion no longer searches for FFmpeg again either.
- **Finishing a file no longer queries the file system for the whole queue.**
  Deciding which folders may already move to the library resolved every target
  path through the file system, twice, after every finished file — on the
  interface thread. The folder follows from the path itself.
- **Scanning resolves each folder once instead of each file.** Whether a file
  lies inside the output folder is decided by its folder; on a network share
  that is one request per season instead of one per episode.

### Fixed

- **Library uploads were not verified byte-for-byte, although the documentation
  said so.** The check compared file sizes. A copy of the right length with the
  wrong contents passed it, and the local folder was deleted afterwards. Every
  file is now read back from the library and compared with its source, block
  by block, *before* it is given its final name — a copy that differs has never
  been in the library under the real name, and a version already there stays
  untouched until the new one is proven. This costs time: each file crosses
  the network twice, so a transfer takes roughly twice as long. One limit
  remains: what is read back is what Windows holds to be the file's contents;
  the data is flushed to the server first, but whether the read is then served
  from the network or from the local cache is up to Windows.
- **Failed sources were only set aside when something was deleted.** Moving
  them to `_InProgress/_Failed` hung off the deletion of verified sources, so
  it never ran with *delete source* switched off, or when every file had
  failed — while the report at the end named a location they were not in.
- **Stopping a transfer waited for the current file to finish**, which for a
  film over a slow share meant minutes. It now stops between blocks and removes
  the partial copy.
- **The transfer progress bar stood still during a large file.** It advanced
  once per file; a folder holding a single film showed the same value from
  start to end. It now follows the bytes, counting both the copy and the
  comparison.
- **FFmpeg downloaded by Amboss was never found.** The download put both
  programs into `%APPDATA%\Amboss\ffmpeg`, but the lookup only searched `PATH`
  and the program folder — so the *FFmpeg is missing* notice came straight back
  after a successful download, on that start and every later one. The folder
  Amboss itself writes to is now part of the search.

## [1.3.5] — 2026-08-26

### Fixed

- **With separate presets active, the quality slider looked usable while the
  codec and preset boxes beside it were greyed out** — although the note below
  says all three are ignored. The code had disabled it all along; the slider
  simply draws itself identically whether enabled or not, unlike the boxes,
  which change completely. It therefore ignored clicks but advertised the
  opposite. Its groove and handle are now drawn in grey while the value does
  not apply.

## [1.3.4] — 2026-08-26

### Changed

- **The download is 30 MB instead of 86, and the window appears in about a
  third of the time.** Measured, then removed: `import qfluentwidgets` alone
  accounted for 4.0 of the 5.2 seconds of startup, almost all of it spent on
  scipy and numpy. They hang off a single file in that library — the Gaussian
  blur behind its Acrylic effect, which Amboss switches off. The library
  provides for their absence itself (`isAcrylicAvailable = False`), so leaving
  them out is its supported configuration rather than a trick. Together with
  Qt's software OpenGL, QML and unused display backends — none of which the
  running process ever loads, verified against its module list — that is 101 MB
  of the 199 MB that used to be unpacked on every single start. Extraction now
  takes 0.6 s instead of 1.8, and the window stands after about 2 s instead of
  2.9 warm, with a larger gap on a cold start.
- **A loading screen covers the wait that remains.** Between double-click and
  window, nothing was visible, and people who do not expect that click a second
  time and start Amboss twice. It appears as soon as the interface library
  begins loading — the expensive part — and follows the Windows light or dark
  setting so nothing flashes white in front of a dark application. Drawn with
  Qt's own means: PyInstaller ships a splash screen of its own, but it pulls
  Tcl/Tk into the executable, some 12 MB, which for an application that just
  lost two thirds of its size is a poor trade.

### Added

- **A test suite in the repository** under `tests/`, covering a real conversion
  through the actual command builder — AV1, H.265, H.264, MKV, multiple audio
  tracks, 4:4:4 with the bit depth preserved — and a smoke test that draws every
  page, every dialog, both themes and both languages with those libraries
  deliberately blocked, so what the executable does is what gets tested.

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
