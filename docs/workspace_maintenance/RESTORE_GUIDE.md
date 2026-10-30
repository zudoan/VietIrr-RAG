# RESTORE & ROLLBACK GUIDE

**VietIRR-RAG Project**  
**Maintenance Scope:** Safe Reorganization of Handover ZIPs and Historical Artifacts  

---

## 1. Relocation Overview
In accordance with the zero-destructive maintenance protocol (`DELETION_ALLOWED = FALSE`):
- 75 historical ZIP handover archives were relocated from workspace root `.` to `archive/handovers/`.
- **Zero files were deleted**.
- All 9310 files in the workspace remain accessible.
- All 585 unit/integration tests and frontend production builds pass without modification.

---

## 2. Rollback Procedure
If any legacy script or external tool requires historical ZIP files to reside in the workspace root directory, execute the following reversible command:

### On Windows PowerShell:
```powershell
# Move all archived handovers back to the workspace root
Get-ChildItem -Path "archive/handovers" -Filter "*.zip" | ForEach-Object {
    Move-Item -Path $_.FullName -Destination "." -Force
}
```

### On Linux / macOS Bash:
```bash
# Move all archived handovers back to the workspace root
mv archive/handovers/*.zip .
```

---

## 3. Extracting and Inspecting Historical Handover Bundles
To inspect or recover source code from any historical handover archive:

```bash
# Example: Inspecting V4.4 Deep Audit Handover
unzip -l archive/handovers/VR4_4_SCIENTIFIC_DEEP_AUDIT_HANDOFF.zip

# Example: Extracting to an isolated temporary folder
mkdir -p tmp/restore_v4_4
unzip -q archive/handovers/VR4_4_SCIENTIFIC_DEEP_AUDIT_HANDOFF.zip -d tmp/restore_v4_4/
```

---

## 4. Integrity Verification After Restore
After any restore or rollback operation, verify workspace integrity using:
```bash
python -c "
import csv, os, hashlib
with open('docs/workspace_maintenance/FILE_RELOCATION_MAP.csv', 'r', encoding='utf-8') as f:
    for row in csv.DictReader(f):
        if row['action'] == 'RELOCATE_TO_ARCHIVE':
            p = row['proposed_destination']
            exists = os.path.exists(p)
            print(f'{row["current_path"]:45s} -> {p} (Exists: {exists})')
"
```
