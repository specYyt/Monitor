__author__ = 'fsy--pc'
#!_*_coding:utf8_*_

from plugins.linux import cpu,host_alive,load,memory,network,sysinfo,uptime

def GetLinuxCpuStatus():
    return cpu.monitor()

def GetLinuxHost_alive():
    return host_alive.monitor()

def GetLinuxLoad():
    return load.monitor()

def GetLinuxNetworkStatus():
    return network.monitor()

def GetLinuxMemStatus():
    return memory.monitor()

def LinuxSysInfo():
    return sysinfo.collect()

def GetLinuxHost_uptime():
    return uptime.monitor()

def WindowsSysInfo():
    from plugins.windows import sysinfo as win_sysinfo
    return win_sysinfo.collect()