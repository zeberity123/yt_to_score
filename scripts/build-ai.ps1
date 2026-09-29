$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$pythonExe = Join-Path $projectRoot '.venv\Scripts\python.exe'
& $pythonExe scripts/prepare-build.py
if ($LASTEXITCODE -ne 0) { throw 'License preparation failed' }
New-Item -ItemType Directory -Path build/runtime -Force | Out-Null
$nodeExe = (Get-Command node.exe -ErrorAction Stop).Source
Copy-Item -LiteralPath $nodeExe -Destination build/runtime/node.exe -Force
& $pythonExe -c "import pathlib,shutil,sys; base=pathlib.Path(sys.base_prefix)/'tcl'; target=pathlib.Path('build/licenses/Tcl-Tk'); target.mkdir(exist_ok=True); [(shutil.copy2(p,target/(p.parent.name+'-'+p.name))) for p in base.glob('*/license*') if p.is_file()]"
foreach ($edition in @('personal', 'api')) {
    $artifact = if ($edition -eq 'personal') { 'AI-Score-Personal-0.1.0' } else { 'AI-Score-API-0.1.0' }
    & $pythonExe -m PyInstaller --noconfirm --onefile --windowed `
        --name $artifact --distpath dist/ai --workpath "build/ai-$edition" --specpath build `
        --paths $projectRoot --icon "$projectRoot/build/assets/app.ico" `
        --add-data "$projectRoot/build/licenses;licenses" --add-data "$projectRoot/build/runtime;runtime" `
        --add-data "$projectRoot/docs/AI_MODE.md;docs" `
        --collect-all verovio --collect-all imageio_ffmpeg --collect-all yt_dlp --collect-all yt_dlp_ejs `
        --exclude-module pytest --exclude-module pymupdf --exclude-module IPython `
        "desktop/ai_$edition.py"
    if ($LASTEXITCODE -ne 0) { throw "Build failed: $edition" }
}
Get-FileHash -Algorithm SHA256 dist/ai/*.exe
Copy-Item -LiteralPath docs/AI_MODE.md -Destination dist/ai/README.md -Force
Copy-Item -LiteralPath docs/THIRD_PARTY.md -Destination dist/ai/THIRD_PARTY.md -Force
New-Item -ItemType Directory -Path dist/ai/licenses -Force | Out-Null
Get-ChildItem -LiteralPath build/licenses | Copy-Item -Destination dist/ai/licenses -Recurse -Force
