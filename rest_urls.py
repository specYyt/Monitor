#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Author:YNG

from django.conf.urls import url,include
from Monitor import views
urlpatterns = [
    #此路由是实现客户端服务端数据交互的路由
    url(r'client/config/(\d+)/$',views.client_configs),
    url(r'client/service/report/$',views.service_data_report),
    #显示主机的状态信息，在前端展示中用到
    url(r'hosts/status/$',views.hosts_status,name='get_hosts_status' ),
    #显示画图数据信息
    url(r'graphs/$',views.graphs_gerator,name='get_graphs' )
]