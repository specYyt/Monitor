#__author__ = 'YNG'
#_*_coding:utf-8_*
from django.conf.urls import url,include
from Monitor import views
urlpatterns = [
    #此路由是实现客户端服务端数据交互的路由
    url(r'^api/', include('Monitor.rest_urls')),

    #实现前端展示
    url(r'^$',views.index),
    url(r'^dashboard/$',views.dashboard,name='dashboard'),
    url(r'^triggers/$', views.triggers, name='triggers'),
    url(r'hosts/$',views.hosts ,name='hosts'),
    url(r'host_groups/$', views.host_groups, name='host_groups'),
    url(r'hosts/(\d+)/$',views.host_detail ,name='host_detail'),
    url(r'trigger_list/$',views.trigger_list ,name='trigger_list'),
]
