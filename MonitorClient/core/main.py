__author__ = 'YNG'
#!_*_coding:utf8_*_

from core import client
class command_handler(object):
    '''
    此类用于实现对命令的解析
    '''
    def __init__(self,sys_args):
        self.sys_args = sys_args
        if len(self.sys_args) <2:exit(self.help_msg())
        self.command_allowcator()

    def command_allowcator(self):
        '''
        命令分发函数，分拣用户输入的不同指令
        '''
        print(self.sys_args[1]) #输出 start
        #通过反射执行函数 ===>start
        if hasattr(self,self.sys_args[1]):
            func=getattr(self,self.sys_args[1])
            return func()
        else:
            print("command does not exit!")
            self.help_msg()

    def help_msg(self):
        valid_commands = '''
        start       start monitor client
        '''
        print(valid_commands)

    def start(self):
        print("going to start the monitor client")
        Client = client.ClientHandler()
        Client.forever_run()
