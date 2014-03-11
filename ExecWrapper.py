__author__ = 'Ondrej Krajicek, ondrej.krajicek@ysoft.com'
__version__ = '1.0'

import win32api
import win32file
import win32job
import win32process
import win32event
import win32security
import argparse
import sys
import string

import win32con


def exec_job(
		executableFile = "",
		commandLine = "",
		cpuAffinityMask = 0,
		priorityClass = 0,
		schedulingClass = 0,
		maxWorkingSetSize = 0,
		perJobUserTimeLimit = 0,
		showWindow = 0
		):
	## Create the job object to assign the limited process to
	hJobObject = win32job.CreateJobObject(None, '')
	print "Created job object to contain the wrapped executable."

	## Set job restrictions
	basicLimits = win32job.QueryInformationJobObject(hJobObject, win32job.JobObjectBasicLimitInformation)
	basicLimits['LimitFlags'] = 0
	print "The default set of limit flags retrieved is: ", basicLimits

	# Working Set Size
	if maxWorkingSetSize > 0:
		basicLimits['MaximumWorkingSetSize'] = maxWorkingSetSize
		basicLimits['MinimumWorkingSetSize'] = 1  # This is going to be adjusted automatically to the default minimum
		basicLimits['LimitFlags'] += win32job.JOB_OBJECT_LIMIT_WORKINGSET
		print "Updated limits to restrict maximum working set size to: %d bytes" % maxWorkingSetSize

	# Affinity Mask
	if cpuAffinityMask != 0:
		(processAffinityMask, systemAffinityMask) = win32process.GetProcessAffinityMask(
			win32process.GetCurrentProcess())
		basicLimits['Affinity'] = systemAffinityMask & cpuAffinityMask
		basicLimits['LimitFlags'] += win32job.JOB_OBJECT_LIMIT_AFFINITY
		print "Updated limits to restrict process with CPU affinity mask: ", basicLimits['Affinity']

	# Priority Class
	basicLimits['PriorityClass'] = priorityClass
	basicLimits['LimitFlags'] += win32job.JOB_OBJECT_LIMIT_PRIORITY_CLASS
	print "Updated limits to restrict process priority class to: ", priorityClass

	# Scheduling Class
	basicLimits['SchedulingClass'] = schedulingClass
	basicLimits['LimitFlags'] += win32job.JOB_OBJECT_LIMIT_SCHEDULING_CLASS
	print "Updated limits to restrict process scheduling class to: ", schedulingClass

	# Max User Time
	basicLimits['PerJobUserTimeLimit'] = perJobUserTimeLimit
	basicLimits['LimitFlags'] += win32job.JOB_OBJECT_LIMIT_JOB_TIME
	print "Updated limits to restrict user CPU time limit to: ", perJobUserTimeLimit

	## Enable required privileges.
	hCurrentProcessToken = win32security.OpenProcessToken(win32process.GetCurrentProcess(),
		win32security.TOKEN_ADJUST_PRIVILEGES | win32security.TOKEN_QUERY)

	incBasePriorityLUID = win32security.LookupPrivilegeValue(None, win32security.SE_INC_BASE_PRIORITY_NAME)
	incQuotaLUID = win32security.LookupPrivilegeValue(None, win32security.SE_INCREASE_QUOTA_NAME)
	incWorkingSetLUID = win32security.LookupPrivilegeValue(None, win32security.SE_INC_WORKING_SET_NAME)

	privileges = [ (incBasePriorityLUID, win32security.SE_PRIVILEGE_ENABLED),
		(incQuotaLUID, win32security.SE_PRIVILEGE_ENABLED),
		(incWorkingSetLUID, win32security.SE_PRIVILEGE_ENABLED) ]
	print "Requesting token privileges: ", privileges

	win32security.AdjustTokenPrivileges(hCurrentProcessToken, 0, privileges)
	print "Access token privileges adjusted."
	win32api.CloseHandle(hCurrentProcessToken)

	## Set the job limits (quota) as defined in the basicLimits dict.
	win32job.SetInformationJobObject(hJobObject, win32job.JobObjectBasicLimitInformation, basicLimits)
	print "Limits updated to: ", basicLimits

	## Create the process with executableFile and commandLine
	startupInfo = win32process.STARTUPINFO()
	startupInfo.dwFlags = win32con.STARTF_USESHOWWINDOW
	startupInfo.wShowWindow = showWindow
	commandLine = string.join(commandLine, ' ')
	hProcess = win32file.INVALID_HANDLE_VALUE
	print "Creating process: %s with command line: %s and startup info: %s" % \
		  (executableFile, commandLine, str(startupInfo))
	(hProcess, hThread, dwProcessId, dwThreadId) = win32process.CreateProcess(
		executableFile, executableFile + ' ' + commandLine, None, None, 0,
	    win32process.CREATE_BREAKAWAY_FROM_JOB, None, None, startupInfo)

	## Assign the process to the job
	win32job.AssignProcessToJobObject(hJobObject, hProcess)
	print "Process assigned to restricted job objects. Limits will be enforced."

	return (hJobObject, hProcess, hThread, dwProcessId, dwThreadId)

def wait_and_kill_process(hProcess, killTimeout):
	hasBeenTerminated = False
	wait = win32event.WaitForSingleObjectEx(hProcess, killTimeout, True)
	print "Waited to kill the process with result: ", wait
	if wait == win32event.WAIT_TIMEOUT:
		win32process.TerminateProcess(hProcess, 1)
		hasBeenTerminated = True
	return hasBeenTerminated


processPriorities = {
	'idle'			: win32process.IDLE_PRIORITY_CLASS,
	'below-normal'	: win32process.BELOW_NORMAL_PRIORITY_CLASS,
	'normal' 		: win32process.NORMAL_PRIORITY_CLASS,
	'above-normal'	: win32process.ABOVE_NORMAL_PRIORITY_CLASS,
	'high'			: win32process.HIGH_PRIORITY_CLASS,
	'realtime'		: win32process.REALTIME_PRIORITY_CLASS
}

showWindowOptions = {
	'hide'		: win32con.SW_HIDE,
	'maximize'	: win32con.SW_MAXIMIZE,
	'minimize'	: win32con.SW_MINIMIZE,
	'normal'	: win32con.SW_NORMAL
}

def read_commandline_from_file(fileName):
	lines = open(fileName, 'r').readlines()
	args = []
	for line in lines:
		## If the argument is quoted string...
		line = string.strip(line)
		if line[0] != '"':
			for a in string.split(line, ' ', 1):
				args.append(a)
		else:
			line = string.strip(line, '"')
			args.append(line)
	return args


def init_argparser():
	parser = argparse.ArgumentParser(description = """
	Execute process with various constraints and restrictions. The process is terminated if the specified
	restriction threshold are exceeded.""")
	parser.add_argument('--version', action='version', version='1.0')
	parser.add_argument('--cpu-mask', action='store', default=0, type=int, dest='cpuMask',
						help='CPU affinity mask. Will be automatically ANDed with the system affinity mask.'
						'Defaults to 0, which means that all available CPUs will be used.')
	parser.add_argument('--priority-class', action='store', default='normal', dest='priorityClass',
						help='Process priority class.', choices=processPriorities)
	parser.add_argument('--scheduling-class', action='store', default=5, type=int, dest='schedulingClass',
						help='Process base scheduling class.', choices=range(0, 10))
	parser.add_argument('--max-user-time', action='store', default=60, type=int, dest='maxUserTime',
						help='Max user CPU time the process can consume in seconds. Defaults to 1 minute.')
	parser.add_argument('--max-working-set', action='store', default=0, type=int, dest='maxWorkingSet',
						help='Maximum working set size in kbytes.')
	parser.add_argument('--time-to-wait', action='store', default=0, type=int, dest='timeToWait',
						help='Absolute time in seconds the process can run.'
						'Zero value meaning that the time is unrestricted. If zero, the wrapper executes the process '
						'and immediatelly terminates. If nonzero, the wrapper waits for the process to finish.')
	parser.add_argument('--show-window', action='store', default='hide', choices=showWindowOptions, dest='showWindow',
						help='Options for showing/hiding window of the executed process.')
	parser.add_argument('executableFile', action='store', help='Executable to run.')
	return parser

def main(args):
	# Parse arguments.
	parser = init_argparser()
	(parsed, rest) = parser.parse_known_args(args)
	parsed.timeToWait *= 1000        # convert from seconds to miliseconds, expected by the API
	parsed.maxUserTime *= 10000000   # convert from seconds to 100 nsec chunks. expected by the API
	parsed.maxWorkingSet *= 1024     # convert to bytes
	parsed.maxWorkingSet += parsed.maxWorkingSet % 4096  # align on next page boundary, 4k pages assumed

	(hJobObject, hProcess, hThread, dwProcessId, dwThreadId) = exec_job(
			executableFile=parsed.executableFile, commandLine=rest, cpuAffinityMask=parsed.cpuMask,
			priorityClass=processPriorities[parsed.priorityClass], schedulingClass=parsed.schedulingClass,
			maxWorkingSetSize=parsed.maxWorkingSet, showWindow=showWindowOptions[parsed.showWindow],
			perJobUserTimeLimit=parsed.maxUserTime)

	print
	print "Spawned process: ", parsed.executableFile
	print "Arguments: ", rest
	print "PID: ", dwProcessId
	print

	hasBeenTerminated = False
	if parsed.timeToWait > 0:
		print "Waiting ", parsed.timeToWait, " miliseconds for process to finish."
		hasBeenTerminated = wait_and_kill_process(hProcess, parsed.timeToWait)
		if hasBeenTerminated:
			print "Process terminated."

	exitCode = win32process.GetExitCodeProcess(hProcess)
	print "Process exit code: ", exitCode
	if exitCode == win32con.STILL_ACTIVE:
		if not hasBeenTerminated:
			print "The process is still running."
	if exitCode == 1816:  # ERROR_NOT_ENOUGH_QUOTA
		print "The process exceeded the specified limits and was terminated."
	win32api.CloseHandle(hProcess)
	win32api.CloseHandle(hJobObject)

	print "Exitting with exit code: ", exitCode
	sys.exit(exitCode)

if __name__ == "__main__":
	try:
		## Read command line arguments from ExecWrapper.conf
		args = read_commandline_from_file("ExecWrapper.conf")
		print "Command line arguments read from ExecWrapper.conf"
		print "Command line arguments: ", args
		print "To skip ExecWrapper.conf, rename or delete it."
		for a in sys.argv[1:]:
			args.append(a)
	except IOError, e:
		args = sys.argv[1:]

	try:
		main(args)

	except:
		print "Error in ExecWrapper: ", sys.exc_type
		print sys.exc_info()
		print



