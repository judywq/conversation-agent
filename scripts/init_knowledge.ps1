#!/usr/bin/env pwsh
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RootDir = Resolve-Path (Join-Path $ScriptDir '..') | Select-Object -ExpandProperty Path

$ComposeFile = if ($env:COMPOSE_FILE) { $env:COMPOSE_FILE } else { 'docker-compose.local.yml' }
$DjangoService = if ($env:DJANGO_SERVICE) { $env:DJANGO_SERVICE } else { 'django' }

$DefaultAnnotationsPath = 'Docs & Files/Sample SA annotation/SA_annotations.json'
$ArgAnnotationsPath = if ($args.Count -ge 1) { $args[0] } else { $null }
$AnnotationsPath = if ($ArgAnnotationsPath) { $ArgAnnotationsPath } elseif ($env:SA_ANNOTATIONS_PATH) { $env:SA_ANNOTATIONS_PATH } else { $DefaultAnnotationsPath }

function Show-Usage {
@"
Usage:
  scripts/init_knowledge.ps1 [path/to/SA_annotations.json]

Environment:
  SA_ANNOTATIONS_PATH   Optional path to SA_annotations.json when no argument is passed.
  COMPOSE_FILE          Docker compose file to use. Defaults to docker-compose.local.yml.
  DJANGO_SERVICE        Django service name. Defaults to django.
  DRY_RUN=1             Parse the data without writing KnowledgeSnippet rows.
  REFRESH_EMBEDDINGS=1  Generate missing embeddings after import. Requires
                        OPENAI_API_KEY unless EMBEDDING_PROVIDER=fake.

Examples:
  scripts/init_knowledge.ps1
  scripts/init_knowledge.ps1 "Docs & Files/Sample SA annotation/SA_annotations.json"
  $env:DRY_RUN=1; scripts/init_knowledge.ps1
"@ | Write-Host
}

if ($args.Count -ge 1 -and ($args[0] -eq '-h' -or $args[0] -eq '--help')) {
  Show-Usage
  exit 0
}

$IsRooted = [System.IO.Path]::IsPathRooted($AnnotationsPath)
if ($IsRooted) {
  $HostAnnotationsPath = (Resolve-Path $AnnotationsPath).Path
  $RootDirWithSep = $RootDir.TrimEnd('\', '/') + [System.IO.Path]::DirectorySeparatorChar
  if (-not $HostAnnotationsPath.StartsWith($RootDirWithSep, [System.StringComparison]::OrdinalIgnoreCase)) {
    Write-Error "ERROR: absolute annotation paths must be inside the repository so Docker can read them:`n  $RootDir"
  }
  $ContainerAnnotationsPath = $HostAnnotationsPath.Substring($RootDirWithSep.Length) -replace '\\', '/'
} else {
  $HostAnnotationsPath = Join-Path $RootDir $AnnotationsPath
  $ContainerAnnotationsPath = $AnnotationsPath -replace '\\', '/'
}

if (-not (Test-Path -LiteralPath $HostAnnotationsPath -PathType Leaf)) {
  Write-Host "ERROR: annotation file not found:" -ForegroundColor Red
  Write-Host "  $HostAnnotationsPath"
  Write-Host ""
  Show-Usage
  exit 1
}

Push-Location $RootDir
try {
  Write-Host "Running migrations with $ComposeFile..."
  docker compose -f $ComposeFile run --rm $DjangoService python manage.py migrate

  $ImportArgs = @('python', 'manage.py', 'import_speech_act_exemplars', $ContainerAnnotationsPath)
  $DryRun = ($env:DRY_RUN -eq '1' -or $env:DRY_RUN -eq 'true')
  if ($DryRun) { $ImportArgs += '--dry-run' }

  Write-Host "Importing Speech Act exemplars from $ContainerAnnotationsPath..."
  docker compose -f $ComposeFile run --rm $DjangoService @ImportArgs

  if ($DryRun) { exit 0 }

  $Refresh = ($env:REFRESH_EMBEDDINGS -eq '1' -or $env:REFRESH_EMBEDDINGS -eq 'true')
  if ($Refresh) {
    Write-Host "Generating missing KnowledgeSnippet embeddings..."
    docker compose -f $ComposeFile run --rm $DjangoService python manage.py refresh_knowledge_embeddings
  }
} finally {
  Pop-Location
}

