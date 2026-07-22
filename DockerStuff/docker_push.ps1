# docker_push.ps1 — Build, tag, test, and push to Docker Hub (Windows)
#
# USAGE:
#   .\docker_push.ps1 youruser
#   .\docker_push.ps1 youruser 1.0.1
#   .\docker_push.ps1 youruser 1.0.1 -NoTest
#   .\docker_push.ps1 youruser 1.0.1 -NoPush

param(
    [Parameter(Mandatory=$true)]
    [string]$DockerHubUser,

    [string]$Version = "latest",
    [switch]$NoTest,
    [switch]$NoPush
)

$ImageName = "$DockerHubUser/ai-pm-copilot"
$LocalTag  = "ai-pm-copilot:latest"

Write-Host ""
Write-Host "╔══════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║   AI PM Copilot — Docker Build & Push        ║" -ForegroundColor Cyan
Write-Host "╚══════════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Image  : $ImageName" -ForegroundColor White
Write-Host "  Version: $Version"   -ForegroundColor White
Write-Host ""

# Step 1 — Build
Write-Host "━━━ [1/4] Building image ━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Yellow
docker build --target production --tag $LocalTag .
if ($LASTEXITCODE -ne 0) { Write-Host "Build FAILED" -ForegroundColor Red; exit 1 }
Write-Host "  ✓ Build complete" -ForegroundColor Green
Write-Host ""

# Step 2 — Smoke test
if (-not $NoTest) {
    Write-Host "━━━ [2/4] Running smoke test ━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Yellow
    docker run --rm $LocalTag python -c @"
from copilot.config import Config
from copilot.memory import MemoryManager
from copilot.agents import AGENT_REGISTRY
from auth.users import _load_users
print('Agents:', list(AGENT_REGISTRY.keys()))
print('Smoke test PASSED')
"@
    if ($LASTEXITCODE -ne 0) { Write-Host "Smoke test FAILED" -ForegroundColor Red; exit 1 }
    Write-Host "  ✓ Smoke test passed" -ForegroundColor Green
    Write-Host ""
} else {
    Write-Host "━━━ [2/4] Smoke test SKIPPED ━━━━━━━━━━━━━━━━━━━━" -ForegroundColor DarkGray
    Write-Host ""
}

# Step 3 — Tag
Write-Host "━━━ [3/4] Tagging ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Yellow
docker tag $LocalTag "${ImageName}:latest"
Write-Host "  ✓ Tagged ${ImageName}:latest" -ForegroundColor Green

if ($Version -ne "latest") {
    docker tag $LocalTag "${ImageName}:${Version}"
    Write-Host "  ✓ Tagged ${ImageName}:${Version}" -ForegroundColor Green
}
Write-Host ""

# Step 4 — Push
if (-not $NoPush) {
    Write-Host "━━━ [4/4] Pushing to Docker Hub ━━━━━━━━━━━━━━━━━" -ForegroundColor Yellow
    docker push "${ImageName}:latest"
    if ($Version -ne "latest") { docker push "${ImageName}:${Version}" }
    Write-Host ""
    Write-Host "  ✓ Image live: docker pull ${ImageName}:${Version}" -ForegroundColor Green
} else {
    Write-Host "━━━ [4/4] Push SKIPPED (-NoPush) ━━━━━━━━━━━━━━━━━" -ForegroundColor DarkGray
}

Write-Host ""
Write-Host "Done." -ForegroundColor Cyan
