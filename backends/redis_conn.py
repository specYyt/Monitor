#!_*_coding:utf8_*_
__author__ = 'YNG'

import django
import redis

#用于生成连接池
def redis_conn(django_settings):
    pool = redis.ConnectionPool(host=django_settings.REDIS_CONN['HOST'],
                                port=django_settings.REDIS_CONN['PORT'],
                                db=2)
    r = redis.Redis(connection_pool = pool)
    return r

