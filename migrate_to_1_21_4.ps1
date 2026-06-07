# Migrates resource pack from custom_model_data overrides (pre-1.21.4)
# to the new items model definition system (1.21.4+/1.21.11).
#
# What this script does:
#   1. Strips the "overrides" array from models/item/*.json (base model defs stay intact)
#   2. Creates assets/minecraft/items/<base>.json for each base item
#   3. Creates assets/minecraft/items/custom/<name>.json for each custom model
#
# Items are then set via: /give @p <item>[minecraft:item_model="minecraft:custom/<name>"]

$ErrorActionPreference = "Stop"
$packRoot  = $PSScriptRoot
$assetsDir = Join-Path $packRoot "assets\minecraft"
$modelsItemDir   = Join-Path $assetsDir "models\item"
$modelsCustomDir = Join-Path $assetsDir "models\custom"
$itemsDir        = Join-Path $assetsDir "items"
$itemsCustomDir  = Join-Path $itemsDir  "custom"

Write-Host ""
Write-Host "=== Minecraft 1.21.4+ Resource Pack Migration ===" -ForegroundColor Cyan
Write-Host "Pack root: $packRoot"
Write-Host ""

# ---------------------------------------------------------------------------
# Step 1: Strip "overrides" from models/item/*.json
# ---------------------------------------------------------------------------
Write-Host "[1/3] Stripping 'overrides' from models/item/*.json ..." -ForegroundColor Yellow

$baseModelFiles = Get-ChildItem -Path $modelsItemDir -Filter "*.json"
$strippedCount  = 0
$skippedCount   = 0

foreach ($file in $baseModelFiles) {
    $json = Get-Content $file.FullName -Raw | ConvertFrom-Json

    if ($null -ne $json.overrides) {
        # Remove the overrides property
        $json.PSObject.Properties.Remove("overrides")
        $json | ConvertTo-Json -Depth 10 | Set-Content $file.FullName -Encoding utf8
        Write-Host "  Stripped overrides: $($file.Name)"
        $strippedCount++
    } else {
        $skippedCount++
    }
}

Write-Host "  Done. Stripped: $strippedCount  Already clean: $skippedCount" -ForegroundColor Green
Write-Host ""

# ---------------------------------------------------------------------------
# Step 2: Create assets/minecraft/items/<base>.json for each base item model
# ---------------------------------------------------------------------------
Write-Host "[2/3] Creating items/<base>.json for base items ..." -ForegroundColor Yellow

if (-not (Test-Path $itemsDir)) {
    New-Item -ItemType Directory -Path $itemsDir | Out-Null
}

$createdBase = 0

foreach ($file in $baseModelFiles) {
    $itemName   = [System.IO.Path]::GetFileNameWithoutExtension($file.Name)
    $outputPath = Join-Path $itemsDir "$itemName.json"

    $content = [ordered]@{
        model = [ordered]@{
            type  = "minecraft:model"
            model = "minecraft:item/$itemName"
        }
    }

    $content | ConvertTo-Json -Depth 5 | Set-Content $outputPath -Encoding utf8
    Write-Host "  Created items/$itemName.json"
    $createdBase++
}

Write-Host "  Done. Created: $createdBase base item definition(s)." -ForegroundColor Green
Write-Host ""

# ---------------------------------------------------------------------------
# Step 3: Create assets/minecraft/items/custom/<name>.json for each custom model
# ---------------------------------------------------------------------------
Write-Host "[3/3] Creating items/custom/<name>.json for custom models ..." -ForegroundColor Yellow

if (-not (Test-Path $itemsCustomDir)) {
    New-Item -ItemType Directory -Path $itemsCustomDir | Out-Null
}

$customModelFiles = Get-ChildItem -Path $modelsCustomDir -Filter "*.json"
$createdCustom    = 0

foreach ($file in $customModelFiles) {
    $modelName  = [System.IO.Path]::GetFileNameWithoutExtension($file.Name)
    $outputPath = Join-Path $itemsCustomDir "$modelName.json"

    $content = [ordered]@{
        model = [ordered]@{
            type  = "minecraft:model"
            model = "minecraft:custom/$modelName"
        }
    }

    $content | ConvertTo-Json -Depth 5 | Set-Content $outputPath -Encoding utf8
    $createdCustom++
}

Write-Host "  Done. Created: $createdCustom custom item definition(s)." -ForegroundColor Green
Write-Host ""

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
Write-Host "=== Migration complete ===" -ForegroundColor Cyan
Write-Host "  Overrides stripped : $strippedCount model file(s)"
Write-Host "  Base item defs     : $createdBase  -> assets/minecraft/items/"
Write-Host "  Custom item defs   : $createdCustom -> assets/minecraft/items/custom/"
Write-Host ""
Write-Host "Give items using:" -ForegroundColor White
Write-Host '  /give @p <base_item>[minecraft:item_model="minecraft:custom/<model_name>"]'
Write-Host ""
Write-Host "Example:"
Write-Host '  /give @p diamond_sword[minecraft:item_model="minecraft:custom/abandoned_knife"]'
