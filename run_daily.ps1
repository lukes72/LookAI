Set-Location $PSScriptRoot

$today = Get-Date -Format "yyyy-MM-dd"
$uv = if ($env:HERMES_UV) { $env:HERMES_UV } else { "uv" }
$cache = Join-Path $PSScriptRoot ".uv-cache"
$commonArgs = @(
    "run", "--python", "3.12",
    "--with", "openpyxl",
    "--with", "requests",
    "--with", "pymupdf",
    "--with", "feedparser",
    "python", "daily_runner.py",
    "--date", $today,
    "--hours", "24"
)

$env:UV_CACHE_DIR = $cache
if ($env:HERMES_SEND -eq "1") {
    & $uv @commonArgs --send
} else {
    & $uv @commonArgs --no-send
}
exit $LASTEXITCODE
