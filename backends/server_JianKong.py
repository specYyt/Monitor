#!_*_coding:utf8_*_
__author__ = 'YNG'

import os,sys
import django
# os.environ.setdefault("DJANGO_SETTINGS_MODULE", "jiankong.settings")
django.setup()
from Monitor.backends import data_ChuFaJianKongBaoJing,trigger_BaoJing
from jiankong import settings

class JianKong(object):
    def __init__(self, argv=None):
        self.argv = argv or sys.argv[:]
        self.prog_name = os.path.basename(self.argv[0])
        self.settings_exception = None
        self.registered_actions = {
            'start':self.start,
            'trigger_watch':self.trigger_watch,
        }

        self.argv_check()

    def argv_check(self):
        '''
        做命令检查
        :return:
        '''
        if len(self.argv) < 2:
            self.help_text()
        if self.argv[1] not in self.registered_actions:
            self.help_text()
        else:
            self.registered_actions[sys.argv[1]]()
    def start(self):
        #不断循环，判断哪些客户端死掉了，无法向服务器端汇报数据；并且将报警信息存放到redis中，并修改主机的状态，在前端显示
        reactor = data_ChuFaJianKongBaoJing.DataHandler(settings)
        reactor.loopping()

    def trigger_watch(self):
        #不断的监听是否有新的trigger到来，负责触发并真正实现向用户发送邮件报警
        trigger_watch = trigger_BaoJing.TriggerHandler(settings)
        trigger_watch.start_watching()

    def help_text(self, commands_only=False):
        if not commands_only:
            print("supported commands as flow:")
            print("         start         ","   判断哪些客户端死掉了")
            print("         trigger_watch ","   负责触发并真正实现向用户发送邮件报警")
            exit()
    def execute(self):
        '''
        run according to user's input
        :return:
        '''
def execute_from_command_line(argv=None):
    """
    调用
    """
    utility = JianKong(argv)
    utility.execute()
