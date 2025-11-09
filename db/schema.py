'''
Descripttion: 
Author: ouchao
Email: ouchao@sendpalm.com
version: 1.0
Date: 2024-07-02 15:29:37
LastEditors: ouchao
LastEditTime: 2025-03-20 11:50:42
'''
from typing import Dict, Any

from bson import ObjectId
from mongoengine import *
import datetime

from mongoengine import Document, StringField, FloatField, DateTimeField, ReferenceField, IntField


def snake_to_camel(snake_str: str) -> str:
    components = snake_str.split('_')
    return components[0] + ''.join(x.title() for x in components[1:])


class BaseDocument(Document):
    meta = {'abstract': True}

    def to_dict(self) -> Dict[str, Any]:
        data = {}
        fields_dict = getattr(self, '_fields', {})
        for field_name, field_type in fields_dict.items():
            value = getattr(self, field_name)
            camel_field_name = snake_to_camel(field_name)
            if isinstance(value, ObjectId):
                data[camel_field_name] = str(value)
            elif isinstance(value, BaseDocument):
                data[camel_field_name] = value.to_dict()
            elif isinstance(value, list):
                data[camel_field_name] = [item.to_dict() if isinstance(item, BaseDocument) else item for item in value]
            else:
                data[camel_field_name] = value
        return data


class User(BaseDocument):
    name = StringField(required=True, unique=True)
    email = StringField(required=True, unique=True)
    password = StringField(required=True,default='')
    platform = StringField(required=False,default="")
    token = StringField(required=False,default="")
    tokens = IntField(default=5000) 
    vip=IntField(default=0)
    vip_expired_at = DateTimeField()  # 会员过期时间
    created_at = DateTimeField(default=datetime.datetime.now)
    updated_at = DateTimeField(default=datetime.datetime.now)
    
    meta = {
        'db_alias': 'default',
        'collection': 'users',
        'indexes': [
            'name',
            'email',
            'platform'
        ]
    }

class UserFile(BaseDocument):
    user = ReferenceField(User, required=True)
    filename = StringField(required=True)
    origin_name = StringField(required=False,default='')
    file_path = StringField(required=True)
    file_type = StringField(required=True)
    lang = StringField(required=True)
    size = StringField(required=False,default=0)
    upload_date = DateTimeField(default=datetime.datetime.now)
    updated_at = DateTimeField(default=datetime.datetime.now)

    meta = {
        'db_alias': 'default',
        'collection': 'user_files',
        'indexes': [
            'user',
            'filename',
            'lang',
            'upload_date'
        ]
    }


class Order(Document):
    user = ReferenceField('User', required=True)
    order_no = StringField(required=True, unique=True)
    amount = FloatField(required=True)
    type = StringField(required=True, choices=['consumption', 'subscription'])  # consumption: 消耗性, subscription: 订阅
    status = StringField(required=True, default='pending', 
                        choices=['pending', 'paid', 'failed', 'cancelled'])  # pending: 待支付, paid: 已支付, failed: 支付失败, cancelled: 已取消
    created_at = DateTimeField(default=datetime.datetime.now)
    paid_at = DateTimeField()
    trade_no = StringField()  # 支付宝交易号
    
    meta = {
        'db_alias': 'default',
        'collection': 'orders',
        'indexes': [
            'user',
            'order_no',
            'status',
            'created_at'
        ]
    }
    
    meta = {
        'db_alias': 'default',
        'collection': 'orders',
        'indexes': [
            'user',
            'order_no',
            'status',
            'created_at'
        ]
    }

