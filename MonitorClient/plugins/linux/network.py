#!_*_coding:utf8_*_
__author__ = 'fsy--pc'

import subprocess

def monitor(first_invoke=1):
    #shell_command = 'sar -n DEV 1 5 | grep -v IFACE | grep Average'
    shell_command = 'sar -n DEV 1 5 | grep -v IFACE | grep 平均时间'
    result = subprocess.Popen(shell_command,shell=True,stdout=subprocess.PIPE).stdout.readlines()
    print(result)
    value_dic = {'status':0,'data':{}}
    for line in result:
        line = line.split()
        nic_name,t_in,t_out = line[1],line[4],line[5]
        value_dic['data'][nic_name] = {"t_in":line[4],"t_out":line[5]}
    return value_dic