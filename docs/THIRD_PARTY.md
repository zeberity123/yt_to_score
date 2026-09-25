# Bundled components

The Windows release includes Electron/Chromium, Python, NumPy, OpenCV, Pillow,
ReportLab, yt-dlp and its dependencies, FFmpeg (via imageio-ffmpeg), and Node.js.
Their licenses and notices are included under `resources/licenses`, alongside
Electron's `LICENSE` and `LICENSES.chromium.html` files in the extracted app.

Upstream source and build information:

- Electron: https://github.com/electron/electron
- Python: https://www.python.org/downloads/source/
- Node.js: https://nodejs.org/en/download
- yt-dlp: https://github.com/yt-dlp/yt-dlp
- yt-dlp EJS: https://github.com/yt-dlp/ejs
- imageio-ffmpeg: https://github.com/imageio/imageio-ffmpeg
- FFmpeg: https://ffmpeg.org/download.html
- Bundled FFmpeg 7.1 Windows essentials build and source links: https://www.gyan.dev/ffmpeg/builds/
- FFmpeg 7.1 source: https://github.com/FFmpeg/FFmpeg/tree/n7.1

FFmpeg is a separate executable invoked by the processing engine. Its own
license and configuration are available with `ffmpeg -L` and `ffmpeg -buildconf`.
The bundled build is GPLv3; its license and build configuration are included in
`resources/licenses/FFmpeg-GPLv3.txt` and `resources/licenses/FFmpeg-build.txt`.
The bundled Python package versions are recorded in `resources/licenses/python-packages.txt`.
