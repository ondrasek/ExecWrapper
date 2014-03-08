@echo off
python setup.py py2exe
pushd dist
del API*
del KERNEL*
del MSWSOCK.dll
popd