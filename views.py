from django.shortcuts import render,HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.core.exceptions import ObjectDoesNotExist
from jiankong import settings
from Monitor.backends import redis_conn, data_ChuFaJianKongBaoJing
from Monitor.backends import data_YouHuaHeCunChu
import json,time
from Monitor import models

#生成全局的redis连接实例，避免每次连接
REDIS_OBJ = redis_conn.redis_conn(settings)

class ClientHandler(object):
    '''
    此类用于实现获取配置信息
    '''
    def __init__(self,client_id):
        self.client_id = client_id
        self.client_configs = {
            "services":{} #定义要监控的服务所需的字典
        }

    def fetch_configs(self):
        '''
        提取监控信息
        由于在数据库定义时：
        host_groups = models.ManyToManyField('HostGroup',blank=True)
        templates = models.ManyToManyField("Template",blank=True)
        主机与主机组，主机与模板都是多对多关系，所以主机监控的服务可能来自主机组，也可能来自模板，因此，这两种情况都要考虑
        :return:
        '''
        try:
            host_obj = models.Host.objects.get(id=self.client_id) #取到主机的对象
            template_list = list(host_obj.templates.select_related()) #取到主机所包含的所有模板，并转换为列表
            for host_group in host_obj.host_groups.select_related():
                template_list.extend(host_group.templates.select_related()) #将主机组所关联的模板加到模板列表
            for template in template_list: #循环每个模板
                for service in template.services.select_related(): #循环每个模板中关联的服务
                    print(service)
                    #将 服务名作为key 、插件名和监控间隔以逗号分隔存入字典
                    self.client_configs['services'][service.name] = [service.plugin_name,service.interval]
        except ObjectDoesNotExist as e:
            pass
        return self.client_configs


def client_configs(request,client_id):
    '''
    此函数用于实现根据客户端请求，返回客户端对应的监控项： 服务名作为key 、插件名和监控间隔以逗号分隔的字典
    :param request:
    :param client_id:
    :return:
    '''
    print("----->",client_id)
    config_obj = ClientHandler(client_id)
    #提取配置
    config = config_obj.fetch_configs()
    if config:
        return HttpResponse(json.dumps(config))


@csrf_exempt
def service_data_report(request):
    '''
    此函数用于实现处理客户端传来的数据： 包括对数据的存储 和 优化，触发监控
    :param request:
    :return:
    '''
    if request.method == 'POST':
        print("----->",request.POST)

        try:
            data = json.loads(request.POST['data']) #获取到客户端的数据
            client_id = request.POST.get('client_id') #获取到客户端的ID
            service_name = request.POST.get('service_name') #获取到服务名

            #做数据监控存储与优化
            data_saveing_obj = data_YouHuaHeCunChu.DataStore(client_id,service_name,data,REDIS_OBJ)

            #触发监控
            host_obj = models.Host.objects.get(id=client_id) #获取到主机对象
            service_triggers = get_host_triggers(host_obj) #获取到主机的所有阈值信息

            trigger_handler = data_ChuFaJianKongBaoJing.DataHandler(settings,connect_redis=False)
            for trigger in service_triggers:
                trigger_handler.load_service_data_and_calulating(host_obj,trigger,REDIS_OBJ) #计算阈值进行报警
            print("service trigger::",service_triggers)
        except IndexError as e:
            print('---------err:',e)

    return HttpResponse(json.dumps("==========report success============"))

def get_host_triggers(host_obj):
    '''
    获取到主机的所有阈值信息
    :param host_obj:
    :return:
    '''
    triggers = []
    for template in host_obj.templates.select_related():
        triggers.extend(template.triggers.select_related() ) #取到主机模板对应的所有trigger，并加入列表
    for group in host_obj.host_groups.select_related():
        for template in group.templates.select_related():
            triggers.extend(template.triggers.select_related()) #取到主机主机组模板对应的所有trigger，并加入列表

    return set(triggers) #去重
def index(request):

    return render(request,'Monitor/monitor/index.html')

def dashboard(request):

    return render(request,'Monitor/monitor/dashboard.html')

def triggers(request):

    return render(request,'Monitor/monitor/triggers.html')

def hosts(request):
    host_list = models.Host.objects.all()
    #print("hosts:",host_list)
    return render(request,'Monitor/monitor/hosts.html',{'host_list':host_list})

def host_detail(request,host_id):
    host_obj = models.Host.objects.get(id=host_id)
    return render(request,'Monitor/monitor/host_detail.html',{'host_obj':host_obj})

def host_groups(request):

    host_groups = models.HostGroup.objects.all()
    return render(request,'Monitor/monitor/host_groups.html',locals())

class GroupStatusSerializer(object):
    def __init__(self,request,redis):
        self.request = request
        self.redis = redis

    def get_all_groups_status(self):

        data_set = [] #store all groups status

        group_objs = models.HostGroup.objects.all()



        for group in group_objs:

            group_data = {
                #'group_id':
                'hosts':[],
                'services':[],
                'triggers':[],
                'events':{'diaster':[],
                          'high':[],
                          'average':[],
                          'warning':[],
                          'info':[]},
                'last_update':None
            }

            host_list  = group.host_set.all()

            template_list = []
            service_list = []

            template_list.extend(group.templates.all())

            for host_obj in host_list:
                template_list.extend(host_obj.templates.select_related())
            #print("group ",group.name,template_list)

            template_list = set(template_list)

            for template_obj in template_list:
                service_list.extend(template_obj.services.all())

            service_list = set(service_list)
            #print("service",service_list)
            group_data['hosts'] =  [{'id':obj.id} for obj in set(host_list)]
            group_data['services'] =  [{'id':obj.id} for obj in set(service_list)]

            #print(group_data)

            group_data['group_id'] = group.id
            data_set.append(group_data)

        print(json.dumps(data_set))

def hostgroups_status(request):
    group_serializer = GroupStatusSerializer(request,REDIS_OBJ)
    group_serializer.get_all_groups_status()

    return HttpResponse('ss')

#用于显示被监控主机的状态
class StatusSerializer(object):
    '''
    此类用于判断主机的状态；为实现前端状态展示做准备
    '''
    def __init__(self,request,redis):
        self.request = request
        self.redis = redis

    def by_hosts(self):
        '''
        处理所有主机
        :return:
        '''
        host_obj_list = models.Host.objects.all()
        host_data_list = []
        for h in host_obj_list:
            host_data_list.append( self.single_host_info(h)  )
        return host_data_list
    def single_host_info(self,host_obj):
        '''
        获取到单个主机的信息
        :param host_obj:
        :return:
        '''
        data = {
            'id': host_obj.id,
            'name':host_obj.name,
            'ip_addr':host_obj.ip_addr,
            'status': host_obj.get_status_display(),
            'last_update':None, #用于在前端展示更新时间
            'triggers':None, #记录各级的监控报警信息
        }

        #for last_uptime
        uptime = self.get_host_uptime(host_obj)
        self.get_triggers(host_obj)
        if uptime:
            data['last_update'] = time.strftime("%Y-%m-%d %H:%M:%S",time.localtime(uptime[1]))

        #for triggers
        data['triggers'] = self.get_triggers(host_obj)

        return  data

    def get_host_uptime(self,host_obj):
        redis_key = 'StatusData_%s_uptime_latest' % host_obj.id
        last_data_point = self.redis.lrange(redis_key,-1,-1)
        if last_data_point:
            last_data_point,last_update = json.loads(last_data_point[0])
            return last_data_point,last_update

    def get_triggers(self,host_obj):
        trigger_keys = self.redis.keys("host_%s_trigger_*" % host_obj.id) #从redis中取到所有 trigger 信息，如：host_2_trigger_2

        ''' (1,'Information'),
        (2,'Warning'),
        (3,'Average'),
        (4,'High'),
        (5,'Diaster'), '''
        trigger_dic = {
            1 : [],
            2 : [],
            3 : [],
            4 : [],
            5 : []
        }

        for trigger_key in trigger_keys:
            trigger_data = self.redis.get(trigger_key)
            '''
            {\"host_id\": 2,
            \"trigger_id\": 2,
            \"positive_expressions\": [{\"calc_res\": true, \"calc_res_val\": 23.0, \"expression_obj\": 4, \"service_item\": null}],
            \"msg\": \"LinuxCpu&Mem\",
            \"time\": \"2017-06-04 22:12:02\",
            \"start_time\": 1496581176.949482,
            \"duration\": 4345}
            '''
            if trigger_key.decode().endswith("None"): #以None结尾，表示为被监控端出现问题，无法向服务端汇报数据
                #trigger_dic[4].append(json.loads(trigger_data.decode()))
                continue
            else:
                trigger_id = trigger_key.decode().split('_')[-1] #取到当前 triger 的报警级别
                trigger_obj = models.Trigger.objects.get(id=trigger_id)
                trigger_dic[trigger_obj.severity].append(json.loads(trigger_data.decode())) #将报警信息加入到报警字典对应的级别中
        return trigger_dic

def hosts_status(request):
    hosts_data_serializer = StatusSerializer(request,REDIS_OBJ)
    hosts_data = hosts_data_serializer.by_hosts()
    return HttpResponse(json.dumps(hosts_data))

class TriggersView(object):
    def __init__(self,request,redis):
        self.request = request
        self.redis = redis
    def fetch_related_filters(self):
        by_host_id = self.request.GET.get('by_host_id')
        host_obj = models.Host.objects.get(id= by_host_id)
        trigger_dic = {}
        if by_host_id:
            trigger_match_keys = "host_%s_trigger_*" % by_host_id
            trigger_keys = self.redis.keys(trigger_match_keys)
            print(trigger_keys)
            for key in trigger_keys:
                data = self.redis.get(key)
                if data:
                    data = json.loads(data.decode())
                    if data.get('trigger_id'):
                        trigger_obj = models.Trigger.objects.get(id=data.get('trigger_id'))
                        data['trigger_obj'] = trigger_obj #为取到的数据字典添加trigger对象
                    data['host_obj'] = host_obj #为取到的数据字典添加host对象
                    trigger_dic[key] = data
        return trigger_dic

def trigger_list(request):
     trigger_handle_obj = TriggersView(request,REDIS_OBJ)
     trigger_data = trigger_handle_obj.fetch_related_filters()
     #trigger_data = {b'host_2_trigger_None': {'host_id': 2, 'trigger_id': None, 'positive_expressions': None, 'msg': "Some thing must be wrong with client [202.207.178.200] , because haven't receive data of service [uptime] for [39.026177644729614]s (interval is [30])", 'time': '2017-06-07 21:29:48', 'start_time': 1496838479.0716944, 'duration': 3710,}, b'host_2_trigger_2': {'host_id': 2, 'trigger_id': 2, 'positive_expressions': [{'calc_res': True, 'calc_res_val': 23.0, 'expression_obj': 4, 'service_item': None}], 'msg': 'LinuxCpu&Mem', 'time': '2017-06-07 21:32:05', 'start_time': 1496836248.6911018, 'duration': 6076,}}
     #trigger_data = {'user_list':{'k1':1,'k2':2},'user':{'a1':3,'a2':4}}
     return render(request,'Monitor/monitor/trigger_list.html',{'trigger_list':trigger_data})

#实现绘图展示
class GraphGenerator2(object):
    '''
    产生流量图
    '''
    def __init__(self,request,redis_obj):
        self.request = request
        self.redis = redis_obj
        self.host_id = self.request.GET.get('host_id') #此id数据由前端传来
        self.time_range = self.request.GET.get('time_range') #此数据由前端传来

    def get_host_graph(self):
        '''
        生成此主机关联的所有图
        :return:
        '''
        host_obj = models.Host.objects.get(id=self.host_id)
        #host_obj = models.Host.objects.get(id=2)
        service_data_dic = {}
        template_list = list(host_obj.templates.select_related()) #取到主机关联的模板，并去重
        for g in host_obj.host_groups.select_related():
            template_list.extend(list(g.templates.select_related()))  #取到主机组关联的模板，并去重
        template_list = set(template_list) #合并所有模板
        for template in template_list:
            for service in template.services.select_related():
                service_data_dic[service.id] = { #取到正常的数据
                    'name':service.name, #监控的服务名
                    'index_data':{},
                    'has_sub_service': service.has_sub_service,
                    'raw_data':[],
                    'items': [item.key for item in service.items.select_related() ]
                }
                '''
                if not service.has_sub_service:
                    for index in service.items.select_related():
                        service_data_dic[service.id]['index_data'][index.key] = {
                            'id': index.id,
                            'name':index.name,
                            'data':[]
                        }
                #else: #like nic service
                '''

        print(service_data_dic)
        #service_data_dic
        #开始取数据
        for service_id,val_dic in service_data_dic.items():
            #if val_dic['has_sub_service'] == False:
            service_redis_key = "StatusData_%s_%s_%s" %(self.host_id,val_dic['name'],self.time_range)
            print('service_redis_key',service_redis_key)
            service_raw_data = self.redis.lrange(service_redis_key,0,-1)
            #[{\"status\": 0, \"MemTotal\": \"1870764\", \"MemUsage\": 396168, \"Cached\": \"305100\", \"MemUsage_p\": \"21\", \"SwapFree\": \"2047996\", \"SwapUsage\": 0, \"SwapTotal\": \"2047996\", \"MemFree\": \"1168368\", \"SwapUsage_p\": \"0\", \"Buffers\": \"1128\"}, 1497795420.1801987]
            service_raw_data =  [item.decode() for item in service_raw_data]
            service_data_dic[service_id]['raw_data'] = service_raw_data
        return service_data_dic #返回取到所有redis中存储的对应时间的对应数据
def graphs_gerator(request):
    graphs_generator = GraphGenerator2(request,REDIS_OBJ)
    graphs_data = graphs_generator.get_host_graph()
    print("graphs_data",graphs_data)
    return HttpResponse(json.dumps(graphs_data))

# #!_*_coding:utf8_*_
# # Create your views here.
# from django.shortcuts import render,HttpResponse
# from django.views.decorators.csrf import csrf_exempt
# from django.core.exceptions import ObjectDoesNotExist
# import json,time
# from jiankong import settings
# from Monitor.backends import redis_conn
# from Monitor.backends import data_YouHuaHeCunChu
# from Monitor import models
# from Monitor.backends import data_ChuFaJianKongBaoJing
#
# #生成全局的redis连接实例，避免每次连接
# REDIS_OBJ = redis_conn.redis_conn(settings)
#
#
# class ClientHandler(object):
#     '''
#     此类用于实现获取配置信息
#     '''
#     def __init__(self,client_id):
#         self.client_id = client_id
#         self.client_configs = {
#             "services":{} #定义要监控的服务所需的字典
#         }
#
#     def fetch_configs(self):
#         '''
#         提取监控信息
#         由于在数据库定义时：
#         host_groups = models.ManyToManyField('HostGroup',blank=True)
#         templates = models.ManyToManyField("Template",blank=True)
#         主机与主机组，主机与模板都是多对多关系，所以主机监控的服务可能来自主机组，也可能来自模板，因此，这两种情况都要考虑
#         :return:
#         '''
#         try:
#             host_obj = models.Host.objects.get(id=self.client_id) #取到主机的对象
#             template_list = list(host_obj.templates.select_related()) #取到主机所包含的所有模板，并转换为列表
#             for host_group in host_obj.host_groups.select_related():
#                 template_list.extend(host_group.templates.select_related()) #将主机组所关联的模板加到模板列表
#             for template in template_list: #循环每个模板
#                 for service in template.services.select_related(): #循环每个模板中关联的服务
#                     print(service)
#                     #将 服务名作为key 、插件名和监控间隔以逗号分隔存入字典
#                     self.client_configs['services'][service.name] = [service.plugin_name,service.interval]
#         except ObjectDoesNotExist as e:
#             pass
#         return self.client_configs
#
# def client_configs(request,client_id):
#     '''
#     此函数用于实现根据客户端请求，返回客户端对应的监控项： 服务名作为key 、插件名和监控间隔以逗号分隔的字典
#     :param request:
#     :param client_id:
#     :return:
#     '''
#     print("----->",client_id)
#     config_obj = ClientHandler(client_id)
#     #提取配置
#     config = config_obj.fetch_configs()
#     if config:
#         return HttpResponse(json.dumps(config))
#
#
# def get_host_triggers(host_obj):
#     '''
#     获取到主机的所有阈值信息
#     :param host_obj:
#     :return:
#     '''
#     triggers = []
#     for template in host_obj.templates.select_related():
#         triggers.extend(template.triggers.select_related() ) #取到主机模板对应的所有trigger，并加入列表
#     for group in host_obj.host_groups.select_related():
#         for template in group.templates.select_related():
#             triggers.extend(template.triggers.select_related()) #取到主机主机组模板对应的所有trigger，并加入列表
#
#     return set(triggers) #去重
# @csrf_exempt
# def service_data_report(request):
#     '''
#     此函数用于实现处理客户端传来的数据： 包括对数据的存储 和 优化，触发监控
#     :param request:
#     :return:
#     '''
#     if request.method == 'POST':
#         try:
#             data = json.loads(request.POST['data']) #获取到客户端的数据
#             client_id = request.POST.get('client_id') #获取到客户端的ID
#             service_name = request.POST.get('service_name') #获取到服务名
#
#             #做数据监控存储与优化
#             data_saveing_obj = data_YouHuaHeCunChu.DataStore(client_id,service_name,data,REDIS_OBJ)
#
#             #触发监控
#
#             host_obj = models.Host.objects.get(id=client_id) #获取到主机对象
#             service_triggers = get_host_triggers(host_obj) #获取到主机的所有阈值信息
#
#             trigger_handler = data_ChuFaJianKongBaoJing.DataHandler(settings,connect_redis=False)
#             for trigger in service_triggers:
#                 trigger_handler.load_service_data_and_calulating(host_obj,trigger,REDIS_OBJ) #计算阈值进行报警
#             print("service trigger::",service_triggers)
#
#         except IndexError as e:
#             print('---------err:',e)
#
#     return HttpResponse(json.dumps("==========report success============"))

# def hosts(request):
#     host_list = models.Host.objects.all()
#     #print("hosts:",host_list)
#     return render(request,'Monitor/monitor/hosts.html',{'host_list':host_list})
#
# def host_detail(request,host_id):
#     host_obj = models.Host.objects.get(id=host_id)
#     return render(request,'Monitor/monitor/host_detail.html',{'host_obj':host_obj})
#
# #用于显示被监控主机的状态
# class StatusSerializer(object):
#     '''
#     此类用于判断主机的状态；为实现前端状态展示做准备
#     '''
#     def __init__(self,request,redis):
#         self.request = request
#         self.redis = redis
#
#     def by_hosts(self):
#         '''
#         处理所有主机
#         :return:
#         '''
#         host_obj_list = models.Host.objects.all()
#         host_data_list = []
#         for h in host_obj_list:
#             host_data_list.append( self.single_host_info(h)  )
#         return host_data_list
#     def single_host_info(self,host_obj):
#         '''
#         获取到单个主机的信息
#         :param host_obj:
#         :return:
#         '''
#         data = {
#             'id': host_obj.id,
#             'name':host_obj.name,
#             'ip_addr':host_obj.ip_addr,
#             'status': host_obj.get_status_display(),
#             'last_update':None, #用于在前端展示更新时间
#             'triggers':None, #记录各级的监控报警信息
#         }
#
#         #for last_uptime
#         uptime = self.get_host_uptime(host_obj)
#         self.get_triggers(host_obj)
#         if uptime:
#             data['last_update'] = time.strftime("%Y-%m-%d %H:%M:%S",time.localtime(uptime[1]))
#
#         #for triggers
#         data['triggers'] = self.get_triggers(host_obj)
#
#         return  data
#
#     def get_host_uptime(self,host_obj):
#         redis_key = 'StatusData_%s_uptime_latest' % host_obj.id
#         last_data_point = self.redis.lrange(redis_key,-1,-1)
#         if last_data_point:
#             last_data_point,last_update = json.loads(last_data_point[0])
#             return last_data_point,last_update
#
#     def get_triggers(self,host_obj):
#         trigger_keys = self.redis.keys("host_%s_trigger_*" % host_obj.id) #从redis中取到所有 trigger 信息，如：host_2_trigger_2
#
#         ''' (1,'Information'),
#         (2,'Warning'),
#         (3,'Average'),
#         (4,'High'),
#         (5,'Diaster'), '''
#         trigger_dic = {
#             1 : [],
#             2 : [],
#             3 : [],
#             4 : [],
#             5 : []
#         }
#
#         for trigger_key in trigger_keys:
#             trigger_data = self.redis.get(trigger_key)
#             '''
#             {\"host_id\": 2,
#             \"trigger_id\": 2,
#             \"positive_expressions\": [{\"calc_res\": true, \"calc_res_val\": 23.0, \"expression_obj\": 4, \"service_item\": null}],
#             \"msg\": \"LinuxCpu&Mem\",
#             \"time\": \"2017-06-04 22:12:02\",
#             \"start_time\": 1496581176.949482,
#             \"duration\": 4345}
#             '''
#             if trigger_key.decode().endswith("None"): #以None结尾，表示为被监控端出现问题，无法向服务端汇报数据
#                 #trigger_dic[4].append(json.loads(trigger_data.decode()))
#                 continue
#             else:
#                 trigger_id = trigger_key.decode().split('_')[-1] #取到当前 triger 的报警级别
#                 trigger_obj = models.Trigger.objects.get(id=trigger_id)
#                 trigger_dic[trigger_obj.severity].append(json.loads(trigger_data.decode())) #将报警信息加入到报警字典对应的级别中
#         return trigger_dic
# def hosts_status(request):
#     hosts_data_serializer = StatusSerializer(request,REDIS_OBJ)
#     hosts_data = hosts_data_serializer.by_hosts()
#     return HttpResponse(json.dumps(hosts_data))
#
# class TriggersView(object):
#     def __init__(self,request,redis):
#         self.request = request
#         self.redis = redis
#     def fetch_related_filters(self):
#         by_host_id = self.request.GET.get('by_host_id')
#         host_obj = models.Host.objects.get(id= by_host_id)
#         trigger_dic = {}
#         if by_host_id:
#             trigger_match_keys = "host_%s_trigger_*" % by_host_id
#             trigger_keys = self.redis.keys(trigger_match_keys)
#             print(trigger_keys)
#             for key in trigger_keys:
#                 data = self.redis.get(key)
#                 if data:
#                     data = json.loads(data.decode())
#                     if data.get('trigger_id'):
#                         trigger_obj = models.Trigger.objects.get(id=data.get('trigger_id'))
#                         data['trigger_obj'] = trigger_obj #为取到的数据字典添加trigger对象
#                     data['host_obj'] = host_obj #为取到的数据字典添加host对象
#                     trigger_dic[key] = data
#         return trigger_dic
# def trigger_list(request):
#      trigger_handle_obj = TriggersView(request,REDIS_OBJ)
#      trigger_data = trigger_handle_obj.fetch_related_filters()
#      #trigger_data = {b'host_2_trigger_None': {'host_id': 2, 'trigger_id': None, 'positive_expressions': None, 'msg': "Some thing must be wrong with client [202.207.178.200] , because haven't receive data of service [uptime] for [39.026177644729614]s (interval is [30])", 'time': '2017-06-07 21:29:48', 'start_time': 1496838479.0716944, 'duration': 3710,}, b'host_2_trigger_2': {'host_id': 2, 'trigger_id': 2, 'positive_expressions': [{'calc_res': True, 'calc_res_val': 23.0, 'expression_obj': 4, 'service_item': None}], 'msg': 'LinuxCpu&Mem', 'time': '2017-06-07 21:32:05', 'start_time': 1496836248.6911018, 'duration': 6076,}}
#      #trigger_data = {'user_list':{'k1':1,'k2':2},'user':{'a1':3,'a2':4}}
#      return render(request,'Monitor/monitor/trigger_list.html',{'trigger_list':trigger_data})
#
# #实现绘图展示
# class GraphGenerator2(object):
#     '''
#     产生流量图
#     '''
#     def __init__(self,request,redis_obj):
#         self.request = request
#         self.redis = redis_obj
#         self.host_id = self.request.GET.get('host_id') #此id数据由前端传来
#         self.time_range = self.request.GET.get('time_range') #此数据由前端传来
#
#     def get_host_graph(self):
#         '''
#         生成此主机关联的所有图
#         :return:
#         '''
#         host_obj = models.Host.objects.get(id=self.host_id)
#         #host_obj = models.Host.objects.get(id=2)
#         service_data_dic = {}
#         template_list = list(host_obj.templates.select_related()) #取到主机关联的模板，并去重
#         for g in host_obj.host_groups.select_related():
#             template_list.extend(list(g.templates.select_related()))  #取到主机组关联的模板，并去重
#         template_list = set(template_list) #合并所有模板
#         for template in template_list:
#             for service in template.services.select_related():
#                 service_data_dic[service.id] = { #取到正常的数据
#                     'name':service.name, #监控的服务名
#                     'index_data':{},
#                     'has_sub_service': service.has_sub_service,
#                     'raw_data':[],
#                     'items': [item.key for item in service.items.select_related() ]
#                 }
#                 '''
#                 if not service.has_sub_service:
#                     for index in service.items.select_related():
#                         service_data_dic[service.id]['index_data'][index.key] = {
#                             'id': index.id,
#                             'name':index.name,
#                             'data':[]
#                         }
#                 #else: #like nic service
#                 '''
#
#         print(service_data_dic)
#         #service_data_dic
#         #开始取数据
#         for service_id,val_dic in service_data_dic.items():
#             #if val_dic['has_sub_service'] == False:
#             service_redis_key = "StatusData_%s_%s_%s" %(self.host_id,val_dic['name'],self.time_range)
#             print('service_redis_key',service_redis_key)
#             service_raw_data = self.redis.lrange(service_redis_key,0,-1)
#             #[{\"status\": 0, \"MemTotal\": \"1870764\", \"MemUsage\": 396168, \"Cached\": \"305100\", \"MemUsage_p\": \"21\", \"SwapFree\": \"2047996\", \"SwapUsage\": 0, \"SwapTotal\": \"2047996\", \"MemFree\": \"1168368\", \"SwapUsage_p\": \"0\", \"Buffers\": \"1128\"}, 1497795420.1801987]
#             service_raw_data =  [item.decode() for item in service_raw_data]
#             service_data_dic[service_id]['raw_data'] = service_raw_data
#         return service_data_dic #返回取到所有redis中存储的对应时间的对应数据
# def graphs_gerator(request):
#     graphs_generator = GraphGenerator2(request,REDIS_OBJ)
#     graphs_data = graphs_generator.get_host_graph()
#     print("graphs_data",graphs_data)
#     return HttpResponse(json.dumps(graphs_data))
