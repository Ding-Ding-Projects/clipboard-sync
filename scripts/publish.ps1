$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\toolchain.ps1"
Set-Location $script:ProjectRoot
if (!(Get-Command gh -ErrorAction SilentlyContinue)) {
    $archive = Get-VerifiedFile 'https://github.com/cli/cli/releases/download/v2.83.2/gh_2.83.2_windows_amd64.zip' 'gh_2.83.2_windows_amd64.zip' 'b95bf2d953e3bf497bb2c0aed97ffcc5ed8471b80f0920d663a92a6111f05135'
    $ghRoot = Join-Path $script:ToolRoot 'gh'
    Expand-Archive -LiteralPath $archive -DestinationPath $ghRoot -Force
    $ghExe = Get-ChildItem $ghRoot -Filter gh.exe -Recurse | Select-Object -First 1
    if (!$ghExe) { throw 'GitHub CLI bootstrap did not produce gh.exe.' }
    $env:PATH = "$($ghExe.DirectoryName);$env:PATH"
}
function Invoke-GitHub([string[]]$Arguments) {
    $output = & gh @Arguments
    if ($LASTEXITCODE -ne 0) { throw "GitHub command failed: $($Arguments[0])" }
    return $output
}
$version = $env:PACKAGE_VERSION
if ($version -notmatch '^\d+\.\d+\.\d+$' -or $env:GITHUB_SHA -notmatch '^[a-f0-9]{40}$') { throw 'Exact release version and source SHA are required.' }
$tag = "v$version-build.$env:GITHUB_RUN_ATTEMPT"
$required = @('ClipboardSync.exe','ClipboardSync-Guide.exe','Setup.exe','RELEASES',"ClipboardSync-$version-full.nupkg",'build-receipt.json')
foreach ($name in $required) { if (!(Test-Path "release/$name")) { throw "Missing release asset: $name" } }
$receipt = Get-Content release/build-receipt.json -Raw | ConvertFrom-Json
if ($receipt.sourceCommit -ne $env:GITHUB_SHA) { throw 'Build receipt does not match publication source.' }
if ($receipt.version -ne $version) { throw 'Build receipt version does not match publication version.' }
foreach ($name in ($required | Where-Object { $_ -ne 'build-receipt.json' })) {
    $expected = $receipt.artifacts.$name
    if (!$expected -or $expected -ne (Get-FileHash "release/$name" -Algorithm SHA256).Hash.ToLowerInvariant()) { throw "Artifact differs from build receipt: $name" }
}
$source = Invoke-GitHub @('api',"repos/$env:GITHUB_REPOSITORY/commits/$env:GITHUB_SHA",'--jq','.sha')
if ($source -ne $env:GITHUB_SHA) { throw 'Source commit readback failed.' }
$ancestry = (Invoke-GitHub @('api',"repos/$env:GITHUB_REPOSITORY/compare/$env:GITHUB_SHA...main")) | ConvertFrom-Json
if ($ancestry.merge_base_commit.sha -ne $env:GITHUB_SHA) { throw 'Release source is not an ancestor of main.' }
$required | ForEach-Object { $hash = (Get-FileHash "release/$_" -Algorithm SHA256).Hash.ToLowerInvariant(); "$hash  $_" } | Set-Content release/SHA256SUMS.txt
$jobs = (Invoke-GitHub @('api',"repos/$env:GITHUB_REPOSITORY/actions/runs/$env:GITHUB_RUN_ID/jobs?per_page=100")) | ConvertFrom-Json
$started = ($jobs.jobs | Where-Object started_at | Sort-Object started_at | Select-Object -First 1).started_at
if (!$started) { throw 'Workflow start time is unavailable.' }
$notes = @"
Windows clipboard receiver with QR phone transfers, automatic local Git history and a self-hosted realtime sync relay.

Download **Setup.exe** for the Squirrel.Windows per-user installation, **ClipboardSync.exe** for portable use, or **ClipboardSync-Guide.exe** for the complete offline guide. RELEASES and the full .nupkg form the unsigned Squirrel package feed.

These artifacts are unsigned and may trigger Windows unknown-publisher or SmartScreen warnings. Native clipboard, firewall and installation acceptance on a user-selected physical Windows machine remains separate from packaging.

This workflow builds, packages and publishes. It runs no tests or lint. Local validation results are recorded in the source documentation; this release does not imply that unrun checks passed.

Source: $env:GITHUB_SHA
Build: https://github.com/$env:GITHUB_REPOSITORY/actions/runs/$env:GITHUB_RUN_ID
Guide: https://ding-ding-projects.github.io/clipboard-sync/
"@
# Code-name metadata is optional and comes only from the public authority.
try {
    $catalog = (Invoke-GitHub @('api','repos/Ding-Ding-Projects/dim-sum-photos/contents/catalog/index.json','-H','Accept: application/vnd.github.raw+json')) | ConvertFrom-Json
    $dishes = if ($catalog.items) { $catalog.items } elseif ($catalog.dishes) { $catalog.dishes } else { @() }
    $previous = (Invoke-GitHub @('api',"repos/$env:GITHUB_REPOSITORY/releases?per_page=100",'--paginate')) -join "`n"
    $photos = (Invoke-GitHub @('api','repos/Ding-Ding-Projects/dim-sum-photos/releases?per_page=100')) | ConvertFrom-Json
    $selected = $null
    foreach ($dish in $dishes) {
        if (!$dish.name.en -or !$dish.name.zhHant -or $previous.Contains([string]$dish.name.en)) { continue }
        $asset = @($photos | Where-Object { $_.tag_name -like 'catalog-v1*' } | ForEach-Object assets | Where-Object { $_.name -eq [IO.Path]::GetFileName([string]$dish.image.path) } | Select-Object -First 1)
        if ($asset.Count) { $selected = "$($dish.name.en) · $($dish.name.zhHant)"; $notes += "`n`nCode name: $selected. [Public photo]($($asset[0].browser_download_url))."; break }
    }
    if (!$selected) { $notes += "`n`nNo unused dish with a verified published photo was resolved; this release uses its version alone." }
} catch { $notes += "`n`nThe public code-name catalogue was unavailable; this release uses its version alone." }
$notesPath = Join-Path $script:ToolRoot 'release-notes.md'
$notes | Set-Content $notesPath -Encoding utf8
$assetPaths = @($required | ForEach-Object { "release/$_" }) + @('release/SHA256SUMS.txt')
Invoke-GitHub (@('release','create',$tag,'--repo',$env:GITHUB_REPOSITORY,'--target',$env:GITHUB_SHA,'--title',"Clipboard Sync $tag",'--notes-file',$notesPath) + $assetPaths) | Out-Host
$completed = [DateTimeOffset]::UtcNow
$elapsed = $completed - [DateTimeOffset]::Parse($started)
$duration = '{0:00}:{1:00}:{2:00}' -f [math]::Floor($elapsed.TotalHours),$elapsed.Minutes,$elapsed.Seconds
$notes += "`n`nWorkflow started: $([DateTimeOffset]::Parse($started).UtcDateTime.ToString('o'))`nWorkflow completed: $($completed.UtcDateTime.ToString('o'))`nWorkflow duration: $duration`nTiming ends after release creation and asset upload; subsequent readback records publication evidence."
$notes | Set-Content $notesPath -Encoding utf8
Invoke-GitHub @('release','edit',$tag,'--repo',$env:GITHUB_REPOSITORY,'--notes-file',$notesPath) | Out-Host
$release = (Invoke-GitHub @('release','view',$tag,'--repo',$env:GITHUB_REPOSITORY,'--json','isDraft,isPrerelease,assets,url')) | ConvertFrom-Json
if ($release.isDraft -or $release.isPrerelease) { throw 'Publication is not a normal release.' }
foreach ($name in ($required + @('SHA256SUMS.txt'))) { if ($name -notin $release.assets.name) { throw "Published release is missing $name" } }
$ref = (Invoke-GitHub @('api',"repos/$env:GITHUB_REPOSITORY/git/ref/tags/$tag")) | ConvertFrom-Json
if ($ref.object.type -ne 'commit' -or $ref.object.sha -ne $env:GITHUB_SHA) { throw 'Release tag does not point directly to the intended source.' }
@{ sourceCommit = $env:GITHUB_SHA; tag = $tag; url = $release.url; startedAt = $started; completedAt = $completed.ToString('o'); duration = $duration; normalRelease = $true } | ConvertTo-Json | Set-Content release/publication-receipt.json
Write-Host "Published $($release.url)"
