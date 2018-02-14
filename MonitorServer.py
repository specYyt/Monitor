#!_*_coding:utf8_*_
__author__ = 'YNG'

'''
此模块用来负责报警；数据来源为发布到redis中的数据
'''
import os,sys

if __name__ == "__main__":
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sys.path.append(base_dir)
    os.environ.setdefault("DJANGO_SETTINGS_MODULE","jiankong.settings")
    from Monitor.backends.server_JianKong import execute_from_command_line

    execute_from_command_line(sys.argv)