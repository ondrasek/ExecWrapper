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