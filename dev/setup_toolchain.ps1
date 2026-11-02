# Downloads toolchain archives on Windows, then installs them into WSL ~/.local
# via setup_toolchain.sh. No sudo required. Safe to re-run.
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$dl = Join-Path $PSScriptRoot '..\..\..\tools\downloads' | Resolve-Path -ErrorAction SilentlyContinue
if (-not $dl) { $dl = New-Item -ItemType Directory -Force (Join-Path $PSScriptRoot '..\..\..\tools\downloads') }
$dl = "$dl"
$files = @{
  'arm-none-eabi.tar.xz' = 'https://developer.arm.com/-/media/Files/downloads/gnu/14.2.rel1/binrel/arm-gnu-toolchain-14.2.rel1-x86_64-arm-none-eabi.tar.xz'
  'uv.tar.gz'            = 'https://github.com/astral-sh/uv/releases/latest/download/uv-x86_64-unknown-linux-gnu.tar.gz'
}
foreach ($name in $files.Keys) {
  $out = Join-Path $dl $name
  if (-not (Test-Path $out)) { Write-Host "Downloading $name"; Invoke-WebRequest -Uri $files[$name] -OutFile $out }
}
$wslDl = (wsl -d Debian -- wslpath -a ($dl -replace '\\', '/')).Trim()
$wslScript = (wsl -d Debian -- wslpath -a ((Join-Path $PSScriptRoot 'setup_toolchain.sh') -replace '\\', '/')).Trim()
wsl -d Debian -- bash -c "sed 's/\r$//' '$wslScript' | bash -s -- '$wslDl'"
