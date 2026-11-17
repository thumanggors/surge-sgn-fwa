@echo off
setlocal
set "DIR=%~dp0"
set "VBS=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\SyncDashboard.vbs"
if not exist "%DIR%password.txt" (
  echo password.txt belum ada di %DIR%
  echo Buat dulu file itu, isi dengan password dashboard pada satu baris, lalu jalankan ulang.
  pause
  exit /b 1
)
> "%VBS%" echo Set sh = CreateObject("WScript.Shell")
>> "%VBS%" echo sh.CurrentDirectory = "%DIR%"
>> "%VBS%" echo sh.Run "pyw -3 sync_github.py", 0, False
wscript "%VBS%"
echo Terpasang. Sinkronisasi berjalan tersembunyi dan otomatis tiap login. Log: %DIR%sync.log
echo Untuk mematikan: jalankan HAPUS-AUTO-SYNC.cmd
pause
endlocal
