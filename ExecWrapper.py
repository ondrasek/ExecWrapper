__author__ = 'Ondrej Krajicek, ondrej.krajicek@ysoft.com'
__version__ = '1.0'

import win32api
import win32file
import win32job
import win32process
import win32con
import win32event
import win32security
import argparse
import sys
import string
import os
import logging

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
	log = logging.getLogger("ExecWrapper.ExecJob")

	## Create the job object to assign the limited process to
	hJobObject = win32job.CreateJobObject(None, '')

	## Set job restrictions
	basicLimits = win32job.QueryInformationJobObject(hJobObject, win32job.JobObjectBasicLimitInformation)
	basicLimits['LimitFlags'] = 0

	# Working Set Size
	if maxWorkingSetSize > 0:
		log.debug("Maximum working set size limit set to: %d", maxWorkingSetSize)
		basicLimits['MaximumWorkingSetSize'] = maxWorkingSetSize
		basicLimits['MinimumWorkingSetSize'] = 1  # This is going to be adjusted automatically to the default minimum
		basicLimits['LimitFlags'] += win32job.JOB_OBJECT_LIMIT_WORKINGSET

	# Affinity Mask
	if cpuAffinityMask != 0:
		(processAffinityMask, systemAffinityMask) = win32process.GetProcessAffinityMask(
			win32process.GetCurrentProcess())
		basicLimits['Affinity'] = systemAffinityMask & cpuAffinityMask
		basicLimits['LimitFlags'] += win32job.JOB_OBJECT_LIMIT_AFFINITY
		log.debug("CPU affinity mask limit set to: %d" % basicLimits['Affinity'])

	# Priority Class
	basicLimits['PriorityClass'] = priorityClass
	basicLimits['LimitFlags'] += win32job.JOB_OBJECT_LIMIT_PRIORITY_CLASS
	log.debug("Process priority class set to: %s" % priorityClass)

	# Scheduling Class
	basicLimits['SchedulingClass'] = schedulingClass
	basicLimits['LimitFlags'] += win32job.JOB_OBJECT_LIMIT_SCHEDULING_CLASS
	log.debug("Scheduling class set to: %s" % schedulingClass)

	# Max User Time
	basicLimits['PerJobUserTimeLimit'] = perJobUserTimeLimit
	basicLimits['LimitFlags'] += win32job.JOB_OBJECT_LIMIT_JOB_TIME
	log.debug("Per Job user time limit set to: %d" % perJobUserTimeLimit)

	## Enable required privileges.
	log.debug("Adjusting token privileges for current process to be able to set the job limits.")
	hCurrentProcessToken = win32security.OpenProcessToken(win32process.GetCurrentProcess(),
		win32security.TOKEN_ADJUST_PRIVILEGES | win32security.TOKEN_QUERY)

	incBasePriorityLUID = win32security.LookupPrivilegeValue(None, win32security.SE_INC_BASE_PRIORITY_NAME)
	incQuotaLUID = win32security.LookupPrivilegeValue(None, win32security.SE_INCREASE_QUOTA_NAME)
	incWorkingSetLUID = win32security.LookupPrivilegeValue(None, win32security.SE_INC_WORKING_SET_NAME)

	privileges = [ (incBasePriorityLUID, win32security.SE_PRIVILEGE_ENABLED),
		(incQuotaLUID, win32security.SE_PRIVILEGE_ENABLED),
		(incWorkingSetLUID, win32security.SE_PRIVILEGE_ENABLED) ]

	win32security.AdjustTokenPrivileges(hCurrentProcessToken, 0, privileges)
	win32api.CloseHandle(hCurrentProcessToken)

	## Set the job limits (quota) as defined in the basicLimits dict.
	win32job.SetInformationJobObject(hJobObject, win32job.JobObjectBasicLimitInformation, basicLimits)

	## Create the process with executableFile and commandLine
	log.info("Starting the process now.")
	startupInfo = win32process.STARTUPINFO()
	startupInfo.dwFlags = win32con.STARTF_USESHOWWINDOW
	startupInfo.wShowWindow = showWindow
	commandLine = string.join(commandLine, ' ')
	hProcess = win32file.INVALID_HANDLE_VALUE
	(hProcess, hThread, dwProcessId, dwThreadId) = win32process.CreateProcess(
		executableFile, executableFile + ' ' + commandLine, None, None, 0,
	    win32process.CREATE_BREAKAWAY_FROM_JOB, None, None, startupInfo)

	## Assign the process to the job
	win32job.AssignProcessToJobObject(hJobObject, hProcess)
	log.info("Process started and assigned to job.")

	return (hJobObject, hProcess, hThread, dwProcessId, dwThreadId)

def wait_and_kill_process(hProcess, dwProcessId, killTimeout):
	log.debug("Attempting to kill process: %d" %  )
	wait = win32event.WaitForSingleObjectEx(hProcess, killTimeout, True)
	if wait == win32event.WAIT_TIMEOUT:
		win32process.TerminateProcess(hProcess, 1)

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
	log = logging.getLogger("ExecWrapper")

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

	log.info("Spawned process: %d" % parsed.executableFile)
	log.info("Arguments: %s" % rest)
	log.info("PID: %d" % dwProcessId)

	if parsed.timeToWait > 0:
		log.warning("Waiting %d miliseconds for process to finish." % parsed.timeToWait)
		wait_and_kill_process(hProcess, dwProcessId, parsed.timeToWait)
		log.warning("Process %d terminated." % dwProcessId)

	exitCode = win32process.GetExitCodeProcess(hProcess)
	log.info("Process exit code: ", exitCode)
	if exitCode == win32con.STILL_ACTIVE:
		log.info("The process is still running.")
	if exitCode == 1816:  # ERROR_NOT_ENOUGH_QUOTA
		log.info("The process exceeded the specified limits and was terminated.")
	win32api.CloseHandle(hProcess)
	win32api.CloseHandle(hJobObject)

	log.warning("Exiting with Exit Code: ", exitCode)
	sys.exit(exitCode)

if __name__ == "__main__":
	try:
		log = logging.getLogger("ExecWrapper")
		log.info("ExecWrapper " + __version__ + " started.")

		## Read command line arguments from ExecWrapper.conf
		args = read_commandline_from_file("ExecWrapper.conf")
		log.warning("Command line arguments read from ExecWrapper.conf")
		log.warning("Command line arguments: %s" % args)
		log.warning("To skip ExecWrapper.conf, rename or delete it.")
		for a in sys.argv[1:]:
			args.append(a)
	except IOError, e:
		args = sys.argv[1:]
	main(args)



