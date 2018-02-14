#!/usr/bin/env python
#coding:utf-8

#yum install sysstat

#http://www.cnblogs.com/howhy/p/6396437.html

# import commands
import subprocess

def monitor(frist_invoke=1):
    #shell_command = 'sar 1 3| grep "^Average:"'
    shell_command = 'sar 1 3| grep "^平均时间:"'
    status,result = subprocess.getstatusoutput(shell_command)
    if status != 0:
        value_dic = {'status': status}
    else:
        value_dic = {}
        user,nice,system = result.split()[2:5]
        v,idle = result.split()[6:]
        value_dic= {
            'user': user,
            'nice': nice,
            'system': system,
            'idle': idle,
            'status': status
        }
    return value_dic

if __name__ == '__main__':
    print(monitor())
