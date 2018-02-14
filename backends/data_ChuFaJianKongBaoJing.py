#!_*_coding:utf8_*_
__author__ = 'YNG'

import time,json,pickle
from jiankong import settings
from Monitor import models
from Monitor.backends import redis_conn
import operator
import redis

class DataHandler(object):
    def __init__(self,django_settings,connect_redis=True):
        self.django_settings = django_settings
        self.poll_interval = 3 #每3秒进行一次全局轮询
        self.config_update_interval = 120 #每120s重新从数据库加载一次配置数据
        self.config_last_loading_time = time.time() #将当前时间设置为最后一次加载配置的时间
        self.global_monitor_dic = {}  #全局监控字典
        self.exit_flag = False
        if connect_redis:
            self.redis = redis_conn.redis_conn(django_settings) #连接redis数据库

    def loopping(self):
        '''
        循环数据；在server_JianKong 中被调用
        :return:
        '''
        #获取到mysql数据库中的配置信息
        self.update_or_load_configs() #生成全局的监控配置dict
        count = 0
        while not self.exit_flag: #永远循环下去
            #print("looping %s".center(50,'-') % count)
            count += 1
            if time.time() - self.config_last_loading_time >= self.config_update_interval: #需要重新加载数据库配置
                #print("need update configs ...")
                print("need update configs ......")
                self.update_or_load_configs()
                print("monitor dic",self.global_monitor_dic)
            if self.global_monitor_dic:
                for h,config_dic in self.global_monitor_dic.items(): #取到主机和他对应的 服务、监控 列表
                    print('handling host:%s' %h)
                    for service_id,val in config_dic['services'].items(): #循环所有要监控的服务
                        #print(service_id,val)
                        service_obj,last_monitor_time = val
                        if time.time() - last_monitor_time >= service_obj.interval: #大于定义的服务监控间隔
                            print("serivce [%s] has reached the monitor interval......" % service_obj.name)
                            self.global_monitor_dic[h]['services'][service_obj.id][1] = time.time() #将last_monitor_time 设置为当前时间

                            self.data_point_validation(h,service_obj) #检测此服务最近的汇报数据
                        else:
                            next_monitor_time = time.time() - last_monitor_time - service_obj.interval
                            print("service [%s] next monitor time is %s" % (service_obj.name,next_monitor_time))

                    if time.time() - self.global_monitor_dic[h]['status_last_check'] >10:
                        #检测 有没有这个机器的trigger,如果没有,把机器状态改成ok
                        trigger_redis_key = "host_%s_trigger*" % (h.id)
                        trigger_keys = self.redis.keys(trigger_redis_key)

                        if len(trigger_keys) ==0: #没有trigger被触发,可以把状态改为ok了
                            h.status = 1
                            h.save()
                    #looping triggers 这里是真正根据用户的配置来监控了
                    #for trigger_id,trigger_obj in config_dic['triggers'].items():
                    #    #print("triggers expressions:",trigger_obj.triggerexpression_set.select_related())
                    #    self.load_service_data_and_calulating(h,trigger_obj)

            time.sleep(self.poll_interval)

    def data_point_validation(self,host_obj,service_obj):
        '''
        仅在这里执行基本数据验证，如果客户端没有在配置的时间间隔内向服务器报告数据，则改变其状态，从而在前端展示
        :param h:
        :param service_obj:
        :return:
        '''
        service_redis_key = "StatusData_%s_%s_latest" %(host_obj.id,service_obj.name) #拼出此服务在redis中存储的对应key
        latest_data_point = self.redis.lrange(service_redis_key,-1,-1)  #取到最近一条数据
        if latest_data_point: #如果数据不为空
            latest_data_point = json.loads(latest_data_point[0].decode()) #取到最近的数据
            #print('laste::::',latest_data_point)
            print("latest data point ====>%s" % latest_data_point)
            latest_service_data,last_report_time = latest_data_point
            monitor_interval = service_obj.interval + self.django_settings.REPORT_LATE_TOLERANCE_TIME #取到监控间隔
            if time.time() - last_report_time > monitor_interval: #超过监控间隔但数据还没汇报过来,可能出现了问题
                no_data_secs =  time.time() - last_report_time #没有汇报数据的时间
                msg = '''Some thing must be wrong with client [%s] , because haven't receive data of service [%s] \
                for [%s]s (interval is [%s])''' %(host_obj.ip_addr, service_obj.name,no_data_secs, monitor_interval)
                self.trigger_notifier(host_obj=host_obj,trigger_id=None,positive_expressions=None,
                                      msg=msg) #将报警信息放到redis中
                print("%s" %msg )
                if service_obj.name == 'uptime': #判断此服务是否是监控主机存活的服务
                    host_obj.status = 3 #unreachable
                    host_obj.save()
                else:
                    host_obj.status = 5 #problem
                    host_obj.save()

            else:
                host_obj.status = 1 #online
                host_obj.save()


        else: # 如果没有数据
            print("no data for serivce [%s] host[%s] at all.." %(service_obj.name,host_obj.name))
            msg = '''no data for serivce [%s] host[%s] at all..''' %(service_obj.name,host_obj.name)
            self.trigger_notifier(host_obj=host_obj,trigger_id=None,positive_expressions=None,msg=msg) #将报警信息放到redis中
            host_obj.status = 5 #problem
            host_obj.save()

    def load_service_data_and_calulating(self,host_obj,trigger_obj,redis_obj):
        '''
        计算阀值进行报警
        :param host_obj:
        :param trigger_obj:
        :param redis_obj: #从外面调用此函数时需传入redis_obj,以减少重复连接
        :return:
        '''
        #StatusData_1_LinuxCPU_10mins
        self.redis = redis_obj #获取redis实例
        calc_sub_res_list= [] #先把每个expression(表达式)的结果算出来放在这个列表里,最后再统一计算这个列表
        positive_expressions = [] #单条表达式的结果（只存为TRUE的），为了让后面知道真正触发监控的具体的服务。
        expression_res_string = '' #表达式结果拼成的字符串

        for expression in trigger_obj.triggerexpression_set.select_related().order_by('id'): #循环所有按id排序的trigger表达式
            print(expression,expression.logic_type)
            expression_process_obj = ExpressionProcess(self,host_obj,expression)
            single_expression_res = expression_process_obj.process() #求单条表达式的结果
            if single_expression_res:
                calc_sub_res_list.append(single_expression_res) #将单条表达式的结果加入列表
                if single_expression_res['expression_obj'].logic_type: #表示不是最后一条
                    #single_expression_res['calc_res']) 表示当前条的结果；single_expression_res['expression_obj'].logic_type 表示与下一条的关系
                    expression_res_string += str(single_expression_res['calc_res']) + ' ' + \
                                             single_expression_res['expression_obj'].logic_type + ' '
                else:
                    expression_res_string += str(single_expression_res['calc_res']) + ' '

                #把所有结果为True的expression提出来,报警时你得知道是谁出问题导致trigger触发了
                if single_expression_res['calc_res'] == True:
                    single_expression_res['expression_obj'] = single_expression_res['expression_obj'].id #要存到redis里,数据库对象转成id
                    positive_expressions.append(single_expression_res) #将触发报警的表达式存到列表中

        print("All trigger res:", trigger_obj.name,expression_res_string)
        if expression_res_string: #结果字符串不为空
            trigger_res = eval(expression_res_string)  #通过自带函数 eval 计算是否触发报警
            print("whole trigger res:", trigger_res )
            if trigger_res:#终于走到这一步,该触发报警了
                print("##############trigger alert:",trigger_obj.severity,trigger_res) #输出trigger的告警级别和计算结果
                self.trigger_notifier(host_obj,trigger_obj.id, positive_expressions,msg=trigger_obj.name) #此函数用于将报警信息存到redis中

    def update_or_load_configs(self):
        '''
        从Mysql数据库加载配置信息
        :return:
        '''
        all_enabled_hosts = models.Host.objects.all() #获取到所有主机
        for h in all_enabled_hosts:
            #处理新添加的主机，为其创建空字典
            if h not in self.global_monitor_dic: #主机对象不在全局监控字典中，表示是新添加的主机
                self.global_monitor_dic[h] = {'services':{}, 'triggers':{}}

            service_list = []
            trigger_list = []
            #取到主机对应的主机组和模板 对应的服务和触发器
            for group in h.host_groups.select_related():
                for template in  group.templates.select_related():
                    service_list.extend(template.services.select_related())
                    trigger_list.extend(template.triggers.select_related())
                for service in service_list:
                    if service.id not in self.global_monitor_dic[h]['services']: #表示第一次循环
                        self.global_monitor_dic[h]['services'][service.id] = [service,0]
                    else:
                        self.global_monitor_dic[h]['services'][service.id][0] = service
                for trigger in trigger_list:
                    self.global_monitor_dic[h]['triggers'][trigger.id] = trigger

            for template in  h.templates.select_related():
                service_list.extend(template.services.select_related())
                trigger_list.extend(template.triggers.select_related())
            for service in service_list:
                if service.id not in self.global_monitor_dic[h]['services']: #第一次循环
                    self.global_monitor_dic[h]['services'][service.id] = [service,0]
                else:
                    self.global_monitor_dic[h]['services'][service.id][0] = service
            for trigger in trigger_list:
                self.global_monitor_dic[h]['triggers'][trigger.id] = trigger
            #print(self.global_monitor_dic[h])
            #通过这个时间来确定是否需要更新主机状态
            self.global_monitor_dic[h].setdefault('status_last_check',time.time())

        self.config_last_loading_time = time.time()
        return True

    def trigger_notifier(self,host_obj,trigger_id, positive_expressions,redis_obj=None,msg=None):
        '''
        将报警信息放到redis中
        :param host_obj:
        :param trigger_id:
        :param positive_expressions: 所有结果为真的表达式
        :param redis_obj:
        :return:
        '''

        if redis_obj: #从外部调用 时才用的到,为了避免重复调用 redis连接
            self.redis = redis_obj
        print("\033[43;1mgoing to send alert msg............\033[0m")
        print('trigger_notifier argv:',host_obj,trigger_id, positive_expressions,redis_obj)
        msg_dic = {'host_id':host_obj.id,
                   'trigger_id':trigger_id,
                   'positive_expressions':positive_expressions,
                   'msg':msg,
                   'time': time.strftime("%Y-%m-%d %H:%M:%S",time.localtime()),
                   'start_time':time.time() ,
                   'duration':None #故障持续时间
                   }
        self.redis.publish(self.django_settings.TRIGGER_CHAN, pickle.dumps(msg_dic))  #将报警信息发布到redis中；因为传的值有数据库对象，接受的一端为Python程序，所以用到pickle

        #先把之前的trigger加载回来,获取上次报警的时间,以统计 故障持续时间
        trigger_redis_key = "host_%s_trigger_%s" % (host_obj.id, trigger_id)
        old_trigger_data = self.redis.get(trigger_redis_key)

        if old_trigger_data:
            old_trigger_data = old_trigger_data.decode()
            trigger_startime = json.loads(old_trigger_data)['start_time']
            msg_dic['start_time'] = trigger_startime
            msg_dic['duration'] = round(time.time() - trigger_startime)
        #同时在redis中纪录这个trigger , 前端页面展示时要统计trigger 个数

        self.redis.set(trigger_redis_key, json.dumps(msg_dic), 300) #一个trigger 纪录 5分钟后会自动清除, 为了在前端统计trigger个数用的

class ExpressionProcess(object):
    '''
    加载数据并计算单条表达式的结果
    '''
    def __init__(self,main_ins,host_obj,expression_obj,specified_item=None):
        '''
        :param main_ins:   DataHandler 实例
        :param host_obj: 具体的host obj
        :param expression_obj: #具体的一条表达式
        :return:
        计算单条表达式的结果
        '''
        self.host_obj = host_obj
        self.expression_obj = expression_obj
        self.main_ins = main_ins
        self.service_redis_key = "StatusData_%s_%s_latest" %(host_obj.id,expression_obj.service.name) #拼出此服务在redis中存储的对应key
        self.time_range = self.expression_obj.data_calc_args.split(',')[0] #获取要从redis中取多长时间的数据,单位为minute 取最近 n 分钟的值; 在输入时规定第一个值为时间间隔
        print("\033[31;1m------>%s\033[0m" % self.service_redis_key)

    def load_data_from_redis(self):
        '''
        从redis中取得数据
        :return:
        '''
        time_in_sec = int(self.time_range) * 60  #取最近 n分钟的数据 下面的+60是默认多取一分钟数据,宁多勿少,多出来的后面会去掉
        approximate_data_points = (time_in_sec + 60) / self.expression_obj.service.interval #获取一个大概要取的值
        #print("approximate dataset nums:", approximate_data_points,time_in_sec)
        try:
            data_range_raw = self.main_ins.redis.lrange(self.service_redis_key,-int(approximate_data_points),-1) #从redis中取到数据
        except redis.exceptions.ResponseError as e:
            print("not enought data for this time range...")
            data_range_raw = self.main_ins.redis.lrange(self.service_redis_key,0,-1) #数据不够，就将所有数据都取出来

        #print("\033[31;1m------>%s\033[0m" % data_range)
        approximate_data_range = [json.loads(i.decode()) for i in data_range_raw] #将取到的数据反序列化
        data_range = [] #精确的需要的数据 列表
        for point  in approximate_data_range: #循环所有的数据
            '''
            [{\"status\": 0, \"data\": {\"eno16777736\": {\"t_in\": \"0.01\", \"t_out\": \"0.00\"}, \"lo\": {\"t_in\": \"0.00\", \"t_out\": \"0.00\"}}}, 1496926682.692853]
            [{\"status\": 0, \"MemTotal\": \"1870764\", \"MemUsage\": 392440, \"Cached\": \"305092\", \"MemUsage_p\": \"20\", \"SwapFree\": \"2047996\", \"SwapUsage\": 0, \"SwapTotal\": \"2047996\", \"MemFree\": \"1172104\", \"SwapUsage_p\": \"0\", \"Buffers\": \"1128\"}, 1496926656.6080413]
            '''
            val,saving_time = point
            if time.time() - saving_time < time_in_sec :#在所定义的时间间隔内，代表数据有效
                data_range.append(point)
        return data_range

    def process(self):
        data = self.load_data_from_redis() #已经按照用户的配置把数据 从redis里取出来了, 比如 最近5分钟,或10分钟的数据
        data_calc_func = getattr(self,'get_%s' % self.expression_obj.data_calc_func)  #拼字符串 ====》 get_avg
        #data_calc_func = self.get_avg...
        single_expression_calc_res = data_calc_func(data) #单条表达式计算，最后返回True或者False ===>[True/False,结果/None,网卡名/None]
        print("---res of single_expression_calc_res ",single_expression_calc_res)
        if single_expression_calc_res: #确保上面的条件 有正确的返回  [True,运算的值，具体服务]
            res_dic = {
                'calc_res':single_expression_calc_res[0], #True or False
                'calc_res_val':single_expression_calc_res[1], #判断根据的值
                'expression_obj':self.expression_obj, #触发器的哪个条件导致的报警
                'service_item':single_expression_calc_res[2], #具体由哪个服务导致的
            }

            print("\033[41;1msingle_expression_calc_res:%s\033[0m" % single_expression_calc_res)
            return res_dic
        else:
            return False

    def get_avg(self,data_set):
        '''
        计算平均值
        :param data_set:
        :return:
        '''
        clean_data_list = []  # only for cpu,mem...
        clean_data_dic = {}  # only for nic... has sub item
        '''
        [{\"status\": 0, \"data\": {\"eno16777736\": {\"t_in\": \"0.01\", \"t_out\": \"0.00\"}, \"lo\": {\"t_in\": \"0.00\", \"t_out\": \"0.00\"}}}, 1496926682.692853]
        [{\"status\": 0, \"MemTotal\": \"1870764\", \"MemUsage\": 392440, \"Cached\": \"305092\", \"MemUsage_p\": \"20\", \"SwapFree\": \"2047996\", \"SwapUsage\": 0, \"SwapTotal\": \"2047996\", \"MemFree\": \"1172104\", \"SwapUsage_p\": \"0\", \"Buffers\": \"1128\"}, 1496926656.6080413]
        '''
        for point in data_set:
            val,save_time = point
            if val:
                if 'data' not in val:#没有子dict，表示非网卡
                    clean_data_list.append(val[self.expression_obj.service_index.key]) #将对应的指标加入列表如：MemUsage、MemUsage_p等
                else: #用于处理网卡这种复杂数据类型
                    for k,v in val['data'].items():
                        if k not in clean_data_dic:
                            clean_data_dic[k]=[]
                        clean_data_dic[k].append(v[self.expression_obj.service_index.key])

        if clean_data_list:  #CPU、memory等的数据
            clean_data_list = [float(i) for i in clean_data_list] #将非网卡数据转换为float类型，如：\"MemUsage\": 392440 的值
            #avg_res = 0 if sum(clean_data_list) == 0 else  sum(clean_data_list)/ len(clean_data_list)
            avg_res = sum(clean_data_list)/ len(clean_data_list) #求得数据的平均值
            #print("\033[46;1m----avg res:%s\033[0m" % avg_res)
            return [self.judge(avg_res), avg_res,None] #调用 judge 与所设置的阀值进行判断，并返回结果

        elif clean_data_dic: #网卡
            for k,v in clean_data_dic.items():
                clean_v_list = [float(i) for i in v]
                avg_res = 0 if sum(clean_v_list) == 0 else sum(clean_v_list) / len(clean_v_list) #求得平均值
                #print("\033[46;1m-%s---avg res:%s\033[0m" % (k,avg_res))
                if self.expression_obj.specified_index_key:#监控了特定的指标,比如有多个网卡,但这里只特定监控eth0
                    if k == self.expression_obj.specified_index_key:#就是监控这个特定指标,match上了
                        #在这里判断是否超越阈值
                        print("test res [%s] [%s] [%s]=%s") %(avg_res, #平均值
                                                            self.expression_obj.operator_type, #运算符
                                                            self.expression_obj.threshold, #阈值
                                                            self.judge(avg_res), #运算结果和阈值运算的结果True 或者 False
                                                            )
                        calc_res = self.judge(avg_res)
                        if calc_res:
                            return  [calc_res,avg_res,k] #后面的循环不用走了,反正 已经成立了一个了
                else:#监控这个服务 的所有项, 比如一台机器的多个网卡, 任意一个超过了阈值,都 算是有问题的
                    calc_res = self.judge(avg_res)
                    if calc_res:
                        return [calc_res,avg_res,k]
                #print('specified monitor key:',self.expression_obj.specified_index_key)
                #print('clean data dic:',k,len(clean_v_list), clean_v_list)
            else: #能走到这一步,代表 上面的循环判段都未成立
                return [False,avg_res,k]
        else:#可能是由于最近这个服务 没有数据 汇报 过来,取到的数据 为空,所以没办法 判断阈值
            return [False,None,None]

    def judge(self,calculated_val):
        '''
        将计算结果和阈值进行比较，判断True或者False
        :param calculated_val: #已经算好的结果,可能是avg(5) or ....
        :return:
        '''
        calc_func = getattr(operator,self.expression_obj.operator_type) #通过反射调用系统自带模块 operator 进行处理  ('eq','='),('lt','<'),('gt','>')
        #calc_func = operator.eq....
        return calc_func(calculated_val,self.expression_obj.threshold) #判断传来的值和阈值的关系，并将结果返回

    def get_hit(self,data_set):
        '''
        return hit times  value of given data set
        :param data_set:
        :return:
        '''
        pass