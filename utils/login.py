import requests
import time
import json


def login_quark(token, config_vars):
    """
    夸克网盘登录
    
    参数:
        token: 登录token
        config_vars: 配置参数
    
    返回:
        bool: 是否登录成功
    """
    if len(config_vars) > 0:
        _config_vars = config_vars.get("data")
    
    s = requests.Session()
    s.headers = {
        'Accept': 'application/json, text/plain, */*',
        'Content-Type': 'application/x-www-form-urlencoded',
        'Origin': 'https://b.quark.cn',
        'Referer': 'https://b.quark.cn/',
        'User-Agent': 'Mozilla/5.0 (Linux; U; Android 15; zh-CN; 2312DRA50C Build/AQ3A.240912.001) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/123.0.6312.80 Quark/7.9.2.771 Mobile Safari/537.36',
        'X-Requested-With': 'com.quark.browser',
        'sec-ch-ua': '"Android WebView";v="123", "Not:A-Brand";v="8", "Chromium";v="123"',
        'sec-ch-ua-mobile': '?1',
        'sec-ch-ua-platform': '"Android"'
    }
    
    # 生成时间戳，用于请求参数
    vcode = int(time.time() * 1000)  # 获取当前时间的毫秒数
    request_id = vcode + 5
    is_login = False
    
    # 构建请求URL和参数
    url = 'https://uop.quark.cn/cas/ajax/loginWithKpsAndQrcodeToken'
    queryParams = config_vars.get("queryParams") + str(int(time.time() * 1000))
    
    # 构建请求数据
    data = {
       'client_id': _config_vars.get("client_id"),
       'v': _config_vars.get("v"),
       'request_id': request_id,
       'sign_wg': _config_vars.get("sign_wg"),
       'kps_wg': _config_vars.get("kps_wg"),
       'vcode': vcode,
       'token': token
    }
    
    # 发送登录请求
    print(data)
    res = s.post(url, data=data, params=queryParams)
    print(res.json())
    
    # 检查登录结果
    if res.json().get('status') == 2000000:
        is_login = True
        
    return is_login