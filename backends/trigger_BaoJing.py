#!_*_coding:utf8_*_
__author__ = 'YNG'

from Monitor.backends import redis_conn
import redis,json
import pickle,time
import smtplib
from email.mime.text import MIMEText
from Monitor import models
from django.core.mail import send_mail
from jiankong import settings

class TriggerHandler(object):

    def __init__(self,django_settings):
        self.django_settings = django_settings
        self.redis = redis_conn.redis_conn(self.django_settings)
        self.alert_counters ={} #记录每个action的触发报警次数
        alert_counters = {
            1: {2:{'counter':0,'last_alert':None},
                4:{'counter':1,'last_alert':None}},  #k是action id, {2:0,3:2}这里面的k是主机id,value是报警次数
        }
    '''
    alert_counters = {
                1(表示action号): {2（主机号）:{'counter':0（报警次数）,'last_alert':None（最后一次报警时间）},
                                  4:{'counter':1,'last_alert':None}},  #k是action id, {2:0,3:2}这里面的k是主机id,value是报警次数
            }
    '''
    def start_watching(self):
        '''
        不断监听是否有新 trigger 的到来
        :return:
        '''

        radio = self.redis.pubsub() #实例化
        radio.subscribe(self.django_settings.TRIGGER_CHAN) #订阅频道
        radio.parse_response() #ready to watch
        print("************start listening new triggers**********")
        self.trigger_count = 0
        while True: #一直循环，监听是否有新的trigger的到来
            msg = radio.parse_response() #获取数据
            self.trigger_consume(msg) #处理数据

    def trigger_consume(self,msg):
        self.trigger_count +=1
        print("************Got a trigger msg [%s]**********" % self.trigger_count)
        trigger_msg = pickle.loads(msg[2])  #取到数据
        action = ActionHandler(trigger_msg,self.alert_counters) #所传的值为 positive_expressions 所对应的数据 和报警次数
        action.trigger_process()


class ActionHandler(object):
    '''
    负责把达到报警条件 的trigger进行分析 ,并根据 action 表中的配置来进行报警
    '''

    def __init__(self,trigger_data,alert_counter_dic):
        self.trigger_data = trigger_data #trigger_id 所对应的数据
        self.alert_counter_dic = alert_counter_dic  #记录每个action的触发报警次数
        self.redis = redis_conn.redis_conn(settings) #连接redis数据库

    def record_log(self,action_obj,action_operation,host_id,trigger_data):
        """record alert log into DB"""
        models.EventLog.objects.create(
            event_type = 0,
            host_id=host_id,
            trigger_id = trigger_data.get('trigger_id'),
            log = trigger_data
        )

    def action_email(self,action_operation_obj,host_id,trigger_data):
        '''
        此函数用于发邮件报警
        :param action_obj: 触发这个报警的action对象 ，这里没有用到
        :param action_operation_obj: 要报警的动作类型 ，这里没有用到
        :param host_id: 要报警的目标主机
        :param trigger_data: 要报警的数据
        :return:
        '''
        global last_time
        mailto_list = [obj.email for obj in action_operation_obj.notifiers.all()] #循环数据库中的通知对象
        subject = "监控"

        #先把之前的trigger加载回来,获取上次报警的时间,以统计 故障持续时间
        trigger_redis_key = "host_%s_trigger_%s" % (trigger_data.get('host_id'), trigger_data.get('trigger_id'))
        old_trigger_data = self.redis.get(trigger_redis_key)
        #print("old_trigger_data",old_trigger_data)
        if old_trigger_data:
            old_trigger_data = old_trigger_data.decode()
            trigger_startime = json.loads(old_trigger_data)['start_time']
            last_time = (time.time() - trigger_startime)

        contents =''' <table width="800" border="0" cellspacing="0" cellpadding="4">
              <tr>
                <td bgcolor="#CECFAD" height="20" style="font-size:14px">*监控报警信息  <a href="http://202.207.178.201:8000/monitor/">监控详情>></a></td>
              </tr>
              <tr>
                <td bgcolor="#EFEBDE" height="100" style="font-size:13px">
                1）主机ID：%s <br>
                2）主机名：%s <br>
                3）告警级别：%s <br>
                4）触发告警的计算结果：%s <br>
                5）触发告警的表达式：%s <br>
                6）报警持续时间：%s <br>
            </td>
              </tr>
            </table>''' % (trigger_data.get('host_id'),
                           models.Host.objects.get(id=trigger_data.get('host_id')).name, #获取到对应的主机名
                           models.Trigger.objects.get(id=trigger_data.get('trigger_id')).severity, #获取到对应的报警级别
                           trigger_data.get('positive_expressions'),
                           trigger_data.get('msg'),
                           last_time)

        if self.send_mail(mailto_list,subject,contents):
            print("done!")
        else:
            print("failed!")

    def send_mail(self,to_list,sub,content):
        mail_host = "smtp.163.com"
        mail_user = "xxxx"
        mail_pass = "xxxx"
        mail_postfix = "163.com"

        me="监控报警"+"<"+mail_user+"@"+mail_postfix+">"
        msg = MIMEText(content,"html","utf-8")
        msg['Subject'] = sub
        msg['From'] = me
        msg['To'] = ",".join(to_list)                #将收件人列表以‘,’分隔
        try:
            server = smtplib.SMTP()
            server.connect(mail_host)                            #连接服务器
            server.login(mail_user,mail_pass)               #登录操作
            server.sendmail(me, to_list, msg.as_string())
            server.close()
            return True
        except Exception as e:
            print(str(e))
            return False

    def trigger_process(self):
        '''
        分析trigger并报警
        :return:
        '''
        #trigger id == None === 》 #既然没有trigger id,直接报警给管理 员；这里是处理客户端出现问题，无法汇报信息到服务器端，在服务端直接输出报警信息
        if self.trigger_data.get('trigger_id') == None:
            if self.trigger_data.get('msg'):
                print(self.trigger_data.get('msg'))
            else:
                print("Invalid trigger data %s" % self.trigger_data)

        else:#正经的trigger 客户端数据汇报了，导致报警要触发了
            #print("\033[33;1m%s\033[0m" %self.trigger_data)

            trigger_id = self.trigger_data.get('trigger_id')
            host_id = self.trigger_data.get('host_id')
            trigger_obj = models.Trigger.objects.get(id=trigger_id)
            actions_set = trigger_obj.action_set.select_related() #找到这个trigger所关联的action list
            print("actions_set:",actions_set)
            matched_action_list = set() # 一个空集合，存放匹配到的action
            for action in actions_set:
                #每个action 都 可以直接 包含多个主机或主机组,循环主机组列表（这里是找主机组里的）
                for hg in action.host_groups.select_related():
                    for h in hg.host_set.select_related():
                        if h.id == host_id:# 这个action适用于此主机
                            matched_action_list.add(action)
                            if action.id not in self.alert_counter_dic: #第一次被 触,先初始化一个action counter dic,用来记录每一个触发报警次数
                                self.alert_counter_dic[action.id] = {} #为action新建一个空字典
                            print("action, ",id(action))
                            if h.id not in self.alert_counter_dic[action.id]:  # 这个主机第一次触发这个action的报警
                                self.alert_counter_dic[action.id][h.id] = {'counter': 0, 'last_alert': time.time()}
                                # self.alert_counter_dic.setdefault(action,{h.id:{'counter':0,'last_alert':time.time()}})
                            else:
                                #如果达到报警触发interval次数，就将报警次数+1
                                if time.time() - self.alert_counter_dic[action.id][h.id]['last_alert'] >= action.interval:
                                    self.alert_counter_dic[action.id][h.id]['counter'] += 1
                                    #self.alert_counter_dic[action.id][h.id]['last_alert'] = time.time()

                                else:
                                    print("没达到alert interval时间,不报警",action.interval,
                                          time.time() - self.alert_counter_dic[action.id][h.id]['last_alert'])
                #每个action 都 可以直接 包含多个主机或主机组,循环主机列表（这里是找主机表里的）
                for host in action.hosts.select_related():
                    if host.id == host_id:   # 这个action适用于此主机
                        matched_action_list.add(action)
                        if action.id not in self.alert_counter_dic:  # 第一次被 触,先初始化一个action counter dic
                            self.alert_counter_dic[action.id] = {}
                        if host.id not in self.alert_counter_dic[action.id]: #这个主机第一次触发这个action的报警
                            # 这儿记成0是为了这个主机第一次触发就直接报警了，因为记成0 （time.time()-0 ）一定大于interval的
                            self.alert_counter_dic[action.id][host.id] ={'counter': 0, 'last_alert': 0}
                            #self.alert_counter_dic.setdefault(action,{h.id:{'counter':0,'last_alert':time.time()}})
                        else:
                            # 如果达到interval时间，就记数+1，记录的是第几次报警。
                            if time.time() - self.alert_counter_dic[action.id][host.id]['last_alert'] >= action.interval:
                                self.alert_counter_dic[action.id][host.id]['counter'] += 1
                                #self.alert_counter_dic[action.id][h.id]['last_alert'] = time.time()
                            else:
                                print("没达到alert interval时间,不报警", action.interval,
                                      time.time() - self.alert_counter_dic[action.id][host.id]['last_alert'])


            print("alert_counter_dic:",self.alert_counter_dic)  #输出每个action的触发报警次数
            print("matched_action_list:",matched_action_list)  #主机 匹配到的所有 action
            for action_obj in matched_action_list: #循环action元组
                if time.time() - self.alert_counter_dic[action_obj.id][host_id]['last_alert'] >= action_obj.interval:
                    #该报警 了
                    print("该报警了.......",time.time() - self.alert_counter_dic[action_obj.id][host_id]['last_alert'],action_obj.interval)
                    for action_operation in action_obj.operations.select_related().order_by('-step'):  #循环action对象对应的报警格式
                        if action_operation.step < self.alert_counter_dic[action_obj.id][host_id]['counter']: #如果报警次数小于此主机统计的报警次数，就报警

                            print("##################alert action:%s" %
                                  action_operation.action_type,action_operation.notifiers) #输出动作类型和通知方式

                            print(self.trigger_data.get('msg'))

                            action_func = getattr(self,'action_%s'% action_operation.action_type)  #拼出报警类型的函数，并使用反射
                            action_func(action_operation,host_id,self.trigger_data)

                            #报完警后更新一下报警时间 ，这样就又重新计算alert interval了
                            self.alert_counter_dic[action_obj.id][host_id]['last_alert'] = time.time()
                            self.record_log(action_obj,action_operation,host_id,self.trigger_data) #记录日志
                        # else:
                        #     print("离下次触发报警的时间还有[%s]s" % )
                        #     print("离下次触发报警的时间还有[%s]s" % )