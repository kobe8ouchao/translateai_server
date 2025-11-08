'''
Descripttion: 
Author: ouchao
Email: ouchao@sendpalm.com
version: 1.0
Date: 2024-07-03 13:47:43
LastEditors: ouchao
LastEditTime: 2024-07-03 13:47:49
'''
from app import create_app
from gevent import pywsgi
import time

if __name__ == '__main__':
    app = create_app()
    server = pywsgi.WSGIServer(('0.0.0.0', 8998), app)

    print(f"Server started at http://{server.address[0]}:{server.address[1]} on {time.strftime('%Y-%m-%d %H:%M:%S')}")

    server.serve_forever()
