# BeastRecon changelog

## V1.1 — 24 October 2026

- Display V1.1 in the window title, app heading, About panel, and copied diagnostics.
- Add a single Preferences / About section with Preferences, About, and Changelog tabs.
- Remember a permanent download folder and default output format across restarts.
- Replace the per-download Save dialog with one-click Download to the chosen folder.
- Preview a link's title, channel/creator, and duration before downloading, when available.
- Load previews in the background after typing pauses, with a manual Preview button and an option to turn automatic preview off.
- Ignore outdated preview responses when the input changes.
- Automatically name saved files after the media title, with safe Windows filenames.
- Keep existing downloads: duplicate titles receive (2), (3), and subsequent numbers.
- Install and update the Windows app in C:\BeastRecon, with C:\BeastRecon\Downloads as the default output folder.
- Preserve preferences and downloaded files during updates; refresh Desktop and Start menu shortcuts to the new location.

## V1.0 — initial development release, 24 October 2026

- Introduce the native desktop app for local files, YouTube links, and other supported media URLs.
- Add MP3, M4A, WAV, FLAC, MP4, and WebM output using FFmpeg and yt-dlp.
- Create a black video background for audio-to-video conversion.
- Add a Windows installer, app icon, Desktop and Start menu shortcuts, and repair/update support.
- Improve YouTube audio downloads by selecting audio-only streams where available.
- Include yt-dlp's official JavaScript solver and Deno runtime for YouTube support.
- Add download percentage, speed, estimated time, and conversion progress.
- Add cancellation, temporary-file cleanup, and protection against overwriting existing files.
- Add Play file, Open folder, copied diagnostics, activity details, and clearer download errors.
- Validate local conversion, URL downloads, merged audio/video streams, and desktop controls with automated tests.

V1.0 includes the unversioned development updates published before V1.1. Live streams, playlists/channels, account verification, and DRM-protected media remain outside the supported workflow.
