#_*_coding:utf-8_*_

import subprocess #subprocess模块用来管理子进程

def monitor(frist_invoke=1):
    value_dic = {}
    shell_command = 'uptime'
    result = subprocess.Popen(shell_command,shell=True,stdout=subprocess.PIPE).stdout.read()

    value_dic= {
        'uptime': result,
        'status': 0
    }
    return value_dic
if __name__ == '__main__':
    print(monitor())
