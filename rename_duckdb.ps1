$baseDir = "S:\jp\stocks_board"
$files = Get-ChildItem -Path $baseDir -Filter *.duckdb

Write-Host "Starting rename process in $baseDir..."

foreach ($file in $files) {
    $oldName = $file.Name
    $baseName = $file.BaseName
    
    # Extract first 4 characters
    if ($baseName.Length -ge 4) {
        $newCode = $baseName.Substring(0, 4)
        $newName = "$newCode.duckdb"
        
        $oldPath = $file.FullName
        $newPath = Join-Path $baseDir $newName
        
        if ($oldName -eq $newName) {
            Write-Host "Skipping $oldName (already in correct format)"
            continue
        }
        
        if (Test-Path $newPath) {
            Write-Warning "Collision: Cannot rename $oldName to $newName. Destination already exists."
        } else {
            Write-Host "Renaming $oldName to $newName"
            Rename-Item -Path $oldPath -NewName $newName
        }
    } else {
        Write-Warning "Skipping $oldName (filename too short to extract 4 characters)"
    }
}

Write-Host "Rename process completed."
