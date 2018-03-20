set /p VERSION=<..\..\pcbasic\data\version.txt
pyinstaller installer.spec
cd ..\..\ansipipe
gcc -s launcher.c -o launcher
cd ..\packaging\windows
move ..\..\ansipipe\launcher.exe dist\pcbasic\pcbasic.com
makensis pcbasic.nsi
ren pcbasic-win32.exe pcbasic-v%VERSION%-win32.exe
rmdir /s /q build
rmdir /s /q dist

