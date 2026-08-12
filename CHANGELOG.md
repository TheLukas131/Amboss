# Changelog

All notable changes to this project are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and
this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
