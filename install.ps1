# Install the handoff skill into every coding CLI on this computer (Windows).
#
#   irm https://raw.githubusercontent.com/chentaymane/handOff/main/install.ps1 | iex
#
# With options for install.py:
#   & ([scriptblock]::Create((irm https://raw.githubusercontent.com/chentaymane/handOff/main/install.ps1))) --dry-run
# Run it again to update. To remove: python "$HOME\.agents\skills\handoff\scripts\handoff.py" skill uninstall
#
# HANDOFF_REF picks a branch or tag (default main); HANDOFF_ARCHIVE points at another .zip (a URL or a file).

function Install-Handoff {
    param([string[]]$Options)
    $ErrorActionPreference = 'Stop'
    $repo = if ($env:HANDOFF_REPO) { $env:HANDOFF_REPO } else { 'chentaymane/handOff' }
    $ref = if ($env:HANDOFF_REF) { $env:HANDOFF_REF } else { 'main' }
    $archive = if ($env:HANDOFF_ARCHIVE) { $env:HANDOFF_ARCHIVE } else { "https://github.com/$repo/archive/$ref.zip" }

    # The first real Python 3.8+; the Microsoft Store placeholder for `python` fails this check.
    $python = $null
    foreach ($candidate in @(@('py', '-3'), @('python'), @('python3'))) {
        $command = Get-Command $candidate[0] -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
        if (-not $command) { continue }
        $prefix = @($candidate | Select-Object -Skip 1)
        try {
            & $command.Source @prefix -c 'import sys; sys.exit(sys.version_info < (3, 8))' 2>$null | Out-Null
            if ($LASTEXITCODE -eq 0) { $python = @($command.Source) + $prefix; break }
        } catch { }
    }
    if (-not $python) {
        Write-Host 'handoff: Python 3.8 or newer is needed and was not found. Get it from https://www.python.org/downloads/' -ForegroundColor Red
        return
    }

    $workdir = Join-Path ([System.IO.Path]::GetTempPath()) ('handoff-' + [guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $workdir | Out-Null
    try {
        Write-Host "Downloading handoff ($ref)..."
        $zip = Join-Path $workdir 'handoff.zip'
        if (Test-Path -LiteralPath $archive -PathType Leaf) {
            Copy-Item -LiteralPath $archive -Destination $zip
        } else {
            [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
            $progress = $ProgressPreference
            $ProgressPreference = 'SilentlyContinue'  # the progress bar makes downloads much slower in Windows PowerShell
            try { Invoke-WebRequest -Uri $archive -OutFile $zip -UseBasicParsing } finally { $ProgressPreference = $progress }
        }
        Expand-Archive -LiteralPath $zip -DestinationPath $workdir
        $installer = Get-ChildItem -LiteralPath $workdir -Directory |
            ForEach-Object { Join-Path $_.FullName 'install.py' } |
            Where-Object { Test-Path -LiteralPath $_ } |
            Select-Object -First 1
        if (-not $installer) { throw "The download has no install.py: $archive" }
        Write-Host ''
        $rest = @($python | Select-Object -Skip 1)
        & $python[0] @rest $installer @Options
    } catch {
        Write-Host "handoff: $($_.Exception.Message)" -ForegroundColor Red
    } finally {
        Remove-Item -LiteralPath $workdir -Recurse -Force -ErrorAction SilentlyContinue
    }
}

Install-Handoff -Options $args
