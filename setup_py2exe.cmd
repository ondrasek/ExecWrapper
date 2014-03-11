@echo on
pushd dist
del. /q
popd
python setup.py py2exe
pushd dist
del API*
del KERNEL*
del MSWSOCK.dll
popd
copy ExecWrapper.conf dist
del /q ExecWrapper.zip
pushd dist
"C:\Program Files\7-zip\7z.exe" a -y -r -bd ..\ExecWrapper.zip *
popd