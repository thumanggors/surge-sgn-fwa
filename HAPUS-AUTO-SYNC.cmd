@echo off
set "VBS=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\SyncDashboard.vbs"
if exist "%VBS%" del "%VBS%"
echo File auto-start dihapus. Proses sync yang sedang berjalan dihentikan lewat Task Manager (cari pythonw.exe),
echo atau otomatis berhenti saat PC restart.
pause
