__author__ = 'YNG'
# !_*_coding:utf8_*_

import time
from conf import settings
import urllib.request
import urllib.parse
# from urllib import *
# from urllib import request,parse,response,error
# import urllib2

import requests
import json
import threading
from plugins import plugin_api


class ClientHandler(object):
    def __init__(self):
        self.monitored_services = {}  # 定义一个空字典，用来保存服务端传来的监控项

    def load_latest_configs(self):
        '''
        加载最近的服务器发来的监控项信息
        :return:
        '''
        request_type = settings.configs['urls']['get_configs'][1]  # 请求类型
        url = "%s/%s" % (settings.configs['urls']['get_configs'][0], settings.configs['HostID'])  # 请求的URL
        latest_configs = self.url_request(request_type, url)  # 获取到最新的监控项信息
        latest_configs = json.loads(latest_configs.decode())
        # 将监控项信息更新到字典中，因为字典天生去重，可以使旧的数据被新的数据直接替换
        self.monitored_services.update(latest_configs)
        print('=================monitored_services========================', self.monitored_services)

    def forever_run(self):
        '''
        此函数用于实现客户端一直监控
        :return:
        '''
        exit_flag = False  # 将退出标记始终设置为假，即永不退出
        config_last_update_time = 0  # 定义上一次更新监控项的时间
        while not exit_flag:
            # 判断监控项是否需要更新
            if time.time() - config_last_update_time > settings.configs['ConfigUpdateInterval']:
                self.load_latest_configs()
                print("Loaded latest config: ", self.monitored_services)
                config_last_update_time = time.time()

            # 开始监控
            # 循环服务端传来的字典
            '''
             {'services': {
            'LinuxCpu': ['GetLinuxCpuStatus',60],
            'LinuxNetwork': ['GetLinuxNetworkStatus',30],
            'LinuxMemory': ['GetLinuxMemoryStatus',90]
            } }
            '''
            for service_name, val in self.monitored_services['services'].items():
                # 长度为2，代表第一次监控 如：'LinuxCpu': ['GetLinuxCpuStatus',60],
                if len(val) == 2:
                    # 第一次监控打上时间戳 0 如：'LinuxCpu': ['GetLinuxCpuStatus',60，0],
                    self.monitored_services['services'][service_name].append(0)
                monitor_interval = val[1]  # 监控间隔
                last_invoke_time = val[2]  # 打上的时间戳，即上次监控的时间
                if time.time() - last_invoke_time > monitor_interval:
                    # 在监控之前将时间戳更新为当前时间
                    self.monitored_services['services'][service_name][2] = time.time()
                    # 启动一个线程开始监控，传入：服务名 和 ['GetLinuxCpuStatus', 60],
                    t = threading.Thread(target=self.invoke_plugin, args=(service_name, val))
                    t.start()
                    print("Going to monitor [%s]" % service_name)
                else:
                    print("Going to monitor [%s] in [%s] secs" % (service_name, (time.time() - last_invoke_time)))
                time.sleep(10)

    def invoke_plugin(self, service_name, val):
        plugin_name = val[0]
        if hasattr(plugin_api, plugin_name):  # 通过反射调用plugins下的相应的插件
            func = getattr(plugin_api, plugin_name)  # 通过反射执行对应的插件
            plugin_callback = func()
            # 定义向服务器端汇报的数据格式
            report_data = {
                'client_id': settings.configs['HostID'],
                'service_name': service_name,
                'data': json.dumps(plugin_callback)
            }
            request_action = settings.configs['urls']['service_report'][1]
            request_url = settings.configs['urls']['service_report'][0]
            print('-----report data:', report_data)
            self.url_request(request_action, request_url, params=report_data)
        else:
            print("\033[31;1mCannot find plugin names [%s] in plugin_api\033[0m" % plugin_name)

    def url_request(self, action, url, **extra_data):
        '''
        实现在客户端接收 服务器端模板信息 和 向服务器端发送根据模板采集到的数据
        :param action: POST/GET
        :param url:
        :param extra_data:
        :return:
        '''
        abs_url = "http://%s:%s/%s" % (settings.configs['Server'],
                                       settings.configs['ServerPort'],
                                       url)  # 拼出请求的url
        if action in ('get', 'GET'):
            print(abs_url, extra_data)
            # try:

            req = urllib.request.Request(abs_url)  # 用要请求的 abs_url 地址创建一个Request对象
            # 通过调用urlopen并传入Request对象，将返回一个相关请求response对象，这个应答对象如同一个文件对象
            req_data = urllib.request.urlopen(req, timeout=settings.configs['RequestTimeout'])
            callback = req_data.read()  # 调用read() 得到返回值
            print("=============>", callback)
            return callback
            # except Exception as e:
            #     exit("\033[[[31;1m%s\033[0m"%e)

        elif action in ('post', 'POST'):
            try:
                data_encode = urllib.parse.urlencode(extra_data['params']).encode("utf-8")
                req = urllib.request.Request(url=abs_url, data=data_encode)
                res_data = urllib.request.urlopen(req, timeout=settings.configs['RequestTimeout'])
                callback = res_data.read()
                callback = json.loads(callback.decode())
                print("\033[31;1m[%s]:[%s]\033[0m response:\n%s" % (action, abs_url, callback))
                return callback
            except Exception as e:
                print('---exec', e)
                exit("\033[[31;1m%s\033[0m" % e)
