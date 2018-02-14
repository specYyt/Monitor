__author__ = 'YNG'
#!_*_coding:utf8_*_

configs = {
    'HostID':2,
    'Server':'10.0.117.40',
    'ServerPort':8000,
    "urls":{
        'get_configs':['monitor/api/client/config','get'],
        'service_report':['monitor/api/client/service/report/','post'],
    },
    'RequestTimeout':60,
    'ConfigUpdateInterval':300, #配置默认监控项更新时间为5分钟
}