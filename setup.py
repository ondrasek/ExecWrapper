from distutils.core import setup
import py2exe

setup(
	name = 'ExecWrapper',
	version = '1.0',
	packages = [''],
	url = 'http://www.ysoft.com',
	license = 'Public Domain',
	author = 'Ondrej Krajicek',
	author_email = 'ondrej.krajicek@ysoft.com',
	description = 'Simple wrapper for executing processes with time / memory restrictions.',
	console = ['ExecWrapper.py']
)
