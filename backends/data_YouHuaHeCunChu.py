#!_*_coding:utf8_*_
__author__ = 'YNG'

from jiankong import settings
import json
import time
import copy

'''
此模块用于实现数据优化：
'''


class DataStore(object):
    def __init__(self, client_id, service_name, data, redis_obj):
        self.client_id = client_id  # 客户端的ID
        self.service_name = service_name  # 服务名称
        self.data = data  # 数据
        self.redis_conn_obj = redis_obj  # redis的连接
        self.process_and_save()  # 此函数用于实现将客户端汇报的数据存储到redis

    def get_data_slice(self, lastest_data_key, optimization_interval, ):
        '''
        所传参数为 StatusData_%s_%s_latest 和 优化间隔 ===》从latest取最近n分钟的数据，此函数可继续优化，无需取全部数据进行判断
        '''
        all_real_data = self.redis_conn_obj.lrange(lastest_data_key, 1, -1)  # 将所有的数据全部取出来；从 1 开始取是因为第 0 个数据为空
        data_set = []
        for item in all_real_data:  # 循环取到的数据
            data = json.loads(item)  # 将数据保存在变量data 中 格式为 （数据 时间）
            if len(data) == 2:  # 保证取到的数据是长度为2的（即包含数据和时间）
                service_data, last_save_time = data
                if time.time() - last_save_time <= optimization_interval:  # 如果 当前时间 - 此数据保存时间  比定义的监控间隔小，说明是所需数据，将其取出
                    data_set.append(data)  # 这些数据是需要优化的数据
                else:
                    pass
        return data_set

    def process_and_save(self):
        '''
        此函数用于实现将数据存储到redis中
        :return:
        '''
        print("\033[42;1m------service data ------------\033[0m")
        # 其中status为插件执行结果，从而判断传回来的数据是否合法
        if self.data['status'] == 0:
            for key, data_series_val in settings.STATUS_DATA_OPTIMIZATION.items():  # 循环时间和所存点数的字典
                data_series_key_in_redis = "StatusData_%s_%s_%s" % (
                self.client_id, self.service_name, key)  # 客户端ID、服务名、监控间隔名 拼成一个大字符串，存入redis
                last_point_from_redis = self.redis_conn_obj.lrange(data_series_key_in_redis, -1, -1)  # 取出redis中的最后一个值
                if not last_point_from_redis:
                    # 如果无数据，就初始化一个数据，值为空、时间为当前时间，下次查的时候就有数据了，可以进行比较
                    self.redis_conn_obj.rpush(data_series_key_in_redis,
                                              json.dumps([None, time.time()]))  # rpush表示从后面往里加数据，相当于列表的append
                if data_series_val[0] == 0:  # 为0的话表示最新的数据，即 'latest':[0,600], 不需要优化，直接存即可
                    self.redis_conn_obj.rpush(data_series_key_in_redis,
                                              json.dumps([self.data, time.time()]))  # 存数据时将数据和当前时间一起存进数据库中
                else:
                    # 取出最后一次存储的数据和最后一次存储的时间
                    #"[{\"load5\": \" 0.00\", \"status\": 0, \"load15\": \" 0.00\", \"load1\": \" 0.00\"}, 1517405582.391635]"
                    last_point_data, last_point_save_time = json.loads(
                        self.redis_conn_obj.lrange(data_series_key_in_redis, -1, -1)[0].decode())

                    if time.time() - last_point_save_time >= data_series_val[0]:  # 如果时间差比自己定义的时间间隔大，需要进行优化
                        lastest_data_key_in_redis = "StatusData_%s_%s_latest" % (self.client_id, self.service_name)

                        # 取最近 n 分钟的数据放到data_set中
                        data_set = self.get_data_slice(lastest_data_key_in_redis, data_series_val[0])
                        if len(data_set) > 0:
                            # 接下来将取到的数据 data_set 交给下面方法处理，计算出优化结果（data_series_key_in_redis是在redis中存储的名字）
                            optimized_data = self.get_optimized_data(data_series_key_in_redis, data_set)
                            if optimized_data:
                                self.save_optimized_data(data_series_key_in_redis, optimized_data)  # 保存优化后的数据
                # 同时确保数据在redis中的存储数量不超过settings中指定 的值
                if self.redis_conn_obj.llen(data_series_key_in_redis) >= data_series_val[1]:
                    self.redis_conn_obj.lpop(data_series_key_in_redis)  # 删除最旧的一个数据（从头开始删除）
        else:
            print("report data is invalid::", self.data)
            raise ValueError

    def save_optimized_data(self, data_series_key_in_redis, optimized_data):
        '''
        将优化后的数据保存到redis中
        :param optimized_data:
        :return:
        '''
        self.redis_conn_obj.rpush(data_series_key_in_redis, json.dumps([optimized_data, time.time()]))

    def get_optimized_data(self, data_set_key, raw_service_data):
        '''
         计算出平均值、最大值、最小值、中位数
        :param data_set_key: 拼接的字符串，例如：StatusData_2_LinuxNetwork_10mins
        :param raw_service_data: 真实的需要优化的数据
        网卡：["[{\"status\": 0, \"data\": {\"eno16777736\": {\"t_in\": \"0.06\", \"t_out\": \"0.00\"}, \"lo\": {\"t_in\": \"0.00\", \"t_out\": \"0.00\"}}}, 1495285185.408843]",...]
        CPU：["[{\"system\": \"0.33\", \"status\": 0, \"idle\": [\"99.67\"], \"user\": \"0.00\", \"nice\": \"0.00\"}, 1495285233.7691886]"...]
        :return:
        '''
        service_data_keys = raw_service_data[0][0].keys()  # 获取到类似 [system,status,idle....]，即获取到传来的数据的具体的项
        first_service_data_point = raw_service_data[0][0]  # 获取到第一个数据，用来创建一个新字典

        optimized_dic = {}  # 定义一个空字典，保存优化后的数据
        if 'data' not in service_data_keys:  # 如果不包含 data ，表示不是网卡数据，是CPU等简单数据
            for key in service_data_keys:
                optimized_dic[key] = []  # optimized_dic[system] = []
            tmp_data_dic = copy.deepcopy(optimized_dic)  # 为了临时存最近n分钟的数据，把他们按照每一个指标都弄成一个列表，来存最近n分钟的数据
            for service_data_item, last_save_time in raw_service_data:  # 循环传来的最近n分钟的数据
                for service_index, v in service_data_item.items():  # 循环每个数据点的数据 service_index 为指标名
                    print('===============>>>>>>', v)
                    try:
                        tmp_data_dic[service_index].append(round(float(v), 2))  # 把这个点的数据存到临时列表中
                    except ValueError as e:
                        pass

            for service_k, v_list in tmp_data_dic.items():  # 循环这个已经按指标分类的字典
                # print(service_k,v_list)
                avg_res = self.get_average(v_list)
                max_res = self.get_max(v_list)
                min_res = self.get_min(v_list)
                mid_res = self.get_mid(v_list)
                optimized_dic[service_k] = [avg_res, max_res, min_res, mid_res]
                print(service_k, optimized_dic[service_k])

        else:  # 用于处理多个网卡的数据
            for service_item_key, v_dic in first_service_data_point['data'].items():
                # service_item_key 相当于网卡名 l0,eth0... ；v_dic 相当于网卡对应的数值 v_dic={t_in:33,t_out:44}
                optimized_dic[service_item_key] = {}  # 把网卡名作为key创建新字典
                for k2, v2 in v_dic.items():
                    optimized_dic[service_item_key][k2] = []  # {eth0:{t_in:[],t_out:[]}}

            tmp_data_dic = copy.deepcopy(optimized_dic)
            if tmp_data_dic:
                # print('tmp data dic:',tmp_data_dic)
                for service_data_item, last_save_time in raw_service_data:  # 循环最近n分钟的数据
                    for service_index, val_dic in service_data_item['data'].items():
                        # service_index 相当于eth0,eth1...；val_dic相当于{t_in:[],t_out:[]}

                        for service_item_sub_key, val in val_dic.items():
                            # service_item_sub_key 相当于t_in,t_out
                            tmp_data_dic[service_index][service_item_sub_key].append(round(float(val), 2))

                for service_k, v_dic in tmp_data_dic.items():
                    for service_sub_k, v_list in v_dic.items():
                        print(service_k, service_sub_k, v_list)
                        avg_res = self.get_average(v_list)
                        max_res = self.get_max(v_list)
                        min_res = self.get_min(v_list)
                        mid_res = self.get_mid(v_list)
                        optimized_dic[service_k][service_sub_k] = [avg_res, max_res, min_res, mid_res]
                        print(service_k, service_sub_k, optimized_dic[service_k][service_sub_k])
            else:
                print("\033[41;1mMust be sth wrong with client report data\033[0m")
        print("optimized empty dic:", optimized_dic)
        return optimized_dic

    def get_average(self, data_set):
        if len(data_set) > 0:
            return sum(data_set) // len(data_set)
        else:
            return 0

    def get_max(self, data_set):
        if len(data_set) > 0:
            return max(data_set)
        else:
            return 0

    def get_min(self, data_set):
        if len(data_set) > 0:
            return min(data_set)
        else:
            return 0

    def get_mid(self, data_set):
        data_set.sort()
        if len(data_set) > 0:
            return data_set[(len(data_set) // 2)]
        else:
            return 0
