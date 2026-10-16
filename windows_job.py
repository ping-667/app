"""Own only the processes we create; Windows closes their tree on exit."""
import ctypes
from ctypes import wintypes as W
import subprocess


class BasicLimits(ctypes.Structure):
    _fields_ = [('process_time', ctypes.c_longlong), ('job_time', ctypes.c_longlong),
                ('flags', W.DWORD), ('min_working_set', ctypes.c_size_t),
                ('max_working_set', ctypes.c_size_t), ('active_limit', W.DWORD),
                ('affinity', ctypes.c_size_t), ('priority', W.DWORD), ('scheduling', W.DWORD)]


class IoCounters(ctypes.Structure):
    _fields_ = [(name, ctypes.c_ulonglong) for name in
                ('read_ops', 'write_ops', 'other_ops', 'read_bytes', 'write_bytes', 'other_bytes')]


class ExtendedLimits(ctypes.Structure):
    _fields_ = [('basic', BasicLimits), ('io', IoCounters),
                ('process_memory', ctypes.c_size_t), ('job_memory', ctypes.c_size_t),
                ('peak_process', ctypes.c_size_t), ('peak_job', ctypes.c_size_t)]


class Accounting(ctypes.Structure):
    _fields_ = [(name, ctypes.c_longlong) for name in ('user', 'kernel', 'period_user', 'period_kernel')] + [
        (name, W.DWORD) for name in ('faults', 'total', 'active', 'terminated')]


class ProcessJob:
    def __init__(self):
        self.kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        self.kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, W.LPCWSTR]
        self.kernel.CreateJobObjectW.restype = W.HANDLE
        self.kernel.SetInformationJobObject.argtypes = [W.HANDLE, ctypes.c_int, ctypes.c_void_p, W.DWORD]
        self.kernel.SetInformationJobObject.restype = W.BOOL
        self.kernel.AssignProcessToJobObject.argtypes = [W.HANDLE, W.HANDLE]
        self.kernel.AssignProcessToJobObject.restype = W.BOOL
        self.kernel.CloseHandle.argtypes = [W.HANDLE]
        self.kernel.CloseHandle.restype = W.BOOL
        self.handle = self.kernel.CreateJobObjectW(None, None)
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())
        limits = ExtendedLimits()
        limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not self.kernel.SetInformationJobObject(self.handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
            error = ctypes.WinError(ctypes.get_last_error())
            self.close()
            raise error

    def start(self, command, **kwargs):
        # Suspend before assignment: even a short-lived launcher cannot escape
        # the job by spawning descendants before AssignProcessToJobObject.
        process = subprocess.Popen(command, creationflags=0x4 | subprocess.CREATE_NO_WINDOW, **kwargs)
        try:
            if not self.kernel.AssignProcessToJobObject(self.handle, W.HANDLE(int(process._handle))):
                raise ctypes.WinError(ctypes.get_last_error())
            ntdll = ctypes.WinDLL('ntdll')
            ntdll.NtResumeProcess.argtypes = [W.HANDLE]
            ntdll.NtResumeProcess.restype = ctypes.c_long
            if ntdll.NtResumeProcess(W.HANDLE(int(process._handle))) < 0:
                raise OSError('无法恢复启动进程')
        except BaseException:
            process.kill()
            process.wait()
            raise
        return process

    def close(self):
        if self.handle:
            self.kernel.CloseHandle(self.handle)
            self.handle = None

    def active(self):
        if not self.handle:
            return False
        query = self.kernel.QueryInformationJobObject
        query.argtypes = [W.HANDLE, ctypes.c_int, ctypes.c_void_p, W.DWORD, ctypes.c_void_p]
        query.restype = W.BOOL
        accounting = Accounting()
        if not query(self.handle, 1, ctypes.byref(accounting), ctypes.sizeof(accounting), None):
            raise ctypes.WinError(ctypes.get_last_error())
        return accounting.active > 0

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
