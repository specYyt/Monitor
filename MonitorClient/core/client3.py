__author__ = 'YNG'
#!_*_coding:utf8_*_

import time
from conf import settings
import urllib
import urllib.request #在python2.7 中使用urllib2
import urllib.parse
import json
import threading
from plugins import plugin_api

class ClientHandler(object):
    def __init__(self):
        self.monitored_services = {} #定义一个空字典，用来保存服务端传来的监控项

    def load_latest_configs(self):
        request_type = settings.configs['urls']['get_configs'][1]
        url = "%s/%s" %(settings.configs['urls']['get_configs'][0],settings.configs['HostID'])
        latest_configs = self.url_request(request_type,url) #获取到最新的监控项信息
        latest_configs = json.loads(latest_configs.decode())
        #latest_configs = json.dumps(latest_configs)
        self.monitored_services.update(latest_configs) #将监控项信息更新到字典中
        print('=================monitored_services========================',self.monitored_services)

    def forever_run(self):
        exit_flag = False
        config_last_update_time = 0 #上一次更新时间
        while not exit_flag:
            #更新监控信息
            if time.time() - config_last_update_time > settings.configs['ConfigUpdateInterval']: #判断配置是否更新
                self.load_latest_configs()
                print("Loaded latest config: ",self.monitored_services)
                config_last_update_time = time.time()
            #开始监控
            for service_name,val in self.monitored_services['services'].items():
                if len(val) == 2: #长度为2，代表第一次监控
                    self.monitored_services['services'][service_name].append(0) #第一次监控打上时间戳 0
                monitor_interval = val[1] #监控间隔
                last_invoke_time = val[2] #打上的时间戳
                if time.time() - last_invoke_time > monitor_interval:
                    print(last_invoke_time,time.time())
                    self.monitored_services['services'][service_name][2] = time.time() #在监控之前将时间戳更新为当前时间
                    t = threading.Thread(target=self.invoke_plugin,args=(service_name,val)) #插件函数，传入服务名和 ['GetLinuxCpuStatus', 60],
                    t.start()
                    print("Going to monitor [%s]"%service_name)
                else:
                    print("Going to monitor [%s] in [%s] secs"%(service_name,(time.time() - last_invoke_time)))
                time.sleep(1)
    def invoke_plugin(self,service_name,val):
        plugin_name = val[0]
        if hasattr(plugin_api,plugin_name):
            func = getattr(plugin_api,plugin_name)
            plugin_callback = func()

            report_data = {
                'client_id':settings.configs['HostID'],
                'service_name':service_name,
                'data':json.dumps(plugin_callback)
            }

            request_action = settings.configs['urls']['service_report'][1]
            request_url = settings.configs['urls']['service_report'][0]
            print('-----report data:',report_data)
            self.url_request(request_action,request_url,params=report_data)
        else:
            print("\033[31;1mCannot find plugin names [%s] in plugin_api\033[0m" %plugin_name)
        print('-----plugin:',val)

    def url_request(self,action,url,**extra_data):
        abs_url = "http://%s:%s/%s" %(settings.configs['Server'],
                                      settings.configs['ServerPort'],
                                      url)
        if action in ('get','GET'):
            print(abs_url,extra_data)
            try:
                req = urllib.request.Request(abs_url)
                req_data = urllib.request.urlopen(req,timeout=settings.configs['RequestTimeout'])
                callback = req_data.read()
                print("=============>",callback)
                return callback
            except urllib.request.URLError as e:
                exit("\033[31;1m%s\033[0m"%e)
        elif action in ('post','POST'):
            try:
                data_encode = urllib.parse.urlencode(extra_data['params'])
                req = urllib.request.Request(url=abs_url,data=data_encode)
                res_data = urllib.request.urlopen(req,timeout=settings.configs['RequestTimeout'])
                callback = res_data.read()
                callback = json.loads(callback)
                print("\033[31;1m[%s]:[%s]\033[0m response:\n%s"%(action,abs_url,callback))
                return callback
            except Exception as e:
                print('---有错误----exec',e)
                exit("\033[31;1m%s\033[0m"%e)