# Standalone Android target

The selected mobile target is a standalone Android application. A phone connected to a desktop Python server does not meet that target.

## Available now

- The shared HTML/CSS/JavaScript interface has responsive capture/review layouts and touch-aware crop selection.
- `web/api.js` contains the platform boundary. There are no Node or Electron imports in the interface.
- `desktop/` provides the Windows Electron shell; `drumscore/server.py` provides its local Python API.
- Portable `.drumscore` bundles contain lossless line images, source frames, crop coordinates, order, inclusion flags, title, and the original line images needed for reset.

## Work needed for an APK

An Android WebView or [Capacitor shell](https://capacitorjs.com/docs) can reuse the interface. The processing adapter must run on the phone rather than assuming `127.0.0.1` is the user's computer.

1. Implement native file picking, persisted access to local videos, app-private working storage, project import/export, and PDF sharing through Android storage APIs.
2. Implement video metadata, seeking, frame capture, playback, and crop-image writes on-device. Preserve full source frames and the portable bundle schema.
3. Port the automatic extraction pipeline (OpenCV staff detection, cleanup, stable-view sampling, median construction, overlap matching, and cancellation) to an Android-supported runtime. Verify output against the same synthetic fixtures as the Python tests.
4. Provide on-device PDF and ZIP export, including Unicode titles. Ensure process interruption cannot corrupt projects.
5. Integrate YouTube downloads separately; local video capture and project review should work offline.
6. Validate on physical Android devices, including storage revocation, rotation, large videos, background interruption, memory pressure, and touch editing.

No Android shell, APK, or on-device processing engine is included in this desktop update. The responsive layout and platform boundary are preparation for that work, not a claim that Android processing already exists.
