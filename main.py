import os
import requests
import sqlite3
import json
from flask import g
from flask import Flask, render_template, request, redirect, url_for, session,make_response,send_from_directory,jsonify
from flask.views import MethodView
from werkzeug.routing import BaseConverter
from utils.login import login_quark
from utils.tools import get_cnb_weburl
from utils.database import CloudDriveDatabase
from datetime import datetime, timezone
import logging
from logging.handlers import RotatingFileHandler


app = Flask(__name__)
app.jinja_env.auto_reload = True

DATABASE = app.config.get('DATABASE') if app.config.get('DATABASE') else 'database.db'

if not os.path.exists('logs'):
    os.mkdir('logs')

file_handler = RotatingFileHandler('logs/app.log', maxBytes=10240, backupCount=10)
file_handler.setFormatter(logging.Formatter(
    '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
))
file_handler.setLevel(logging.INFO)

app.logger.addHandler(file_handler)
app.logger.setLevel(logging.INFO)
app.logger.info('Flask App startup')


def get_db():
    # 从全局对象 g 中获取数据库连接
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = CloudDriveDatabase(DATABASE)
        db.row_factory = sqlite3.Row
    return db


# 定义数据库注入装饰器
def inject_db(f):
    def decorated_function(*args, **kwargs):
        db = get_db()
        # 将 db 作为第一个参数传递
        return f(db, *args, **kwargs)
    return decorated_function


@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()


@app.route("/", methods=["GET", "POST"])
def index():
    return render_template('index.html')


#falsk中重定向
@app.route('/profile/')
def profile():
  if request.args.get('name'):
    return '个人中心页面'
  else:
    # return redirect(url_for('login'))
    return redirect(url_for('index'),code=302)



@app.route('/login',methods=['POST'])
def login():
    # 获取POST请求中的JSON数据
    data = request.get_json()
    token = data.get('token')
    link_uuid = data.get('link_uuid')
    
    if not token:
        print('缺少token参数')
        return jsonify({"status": False, "message": "缺少token参数"})
    

    
    
    # 如果有外链UUID，则更新其使用次数
    if link_uuid:
        db = get_db()
        # 获取当前外链信息
        link_info = db.get_external_link_by_uuid(link_uuid)
        
        if link_info:
            # 获取当前已使用次数和总次数
            used_quota = link_info.get('used_quota', 0)
            total_quota = link_info.get('total_quota', 0)
            exdrive_id = link_info.get('drive_id',0)
            
            # 确保不超过总次数
            if used_quota < total_quota:

                # 根据exdrive_id从drive_providers表查询config_vars
                drive_info = db.get_user_drive(exdrive_id)
                #print(drive_info)
                if drive_info:
                    config_vars = drive_info.get("login_config")
                    status = login_quark(token,config_vars)

                # 增加使用次数
                new_used_quota = used_quota + 1
                update_success = db.update_external_link_quota(link_uuid, new_used_quota)
                if update_success:
                    print(f"已更新外链 {link_uuid} 的使用次数: {int(new_used_quota)}/{int(total_quota)}")
    
    return jsonify({"status": status})

@app.route('/exlink/<string:id>')
def qrlink(id):
    db = get_db()
    data = {"status": False}
    
    # 获取外链信息
    link_info = db.get_external_link_by_uuid(id)
    
    if link_info:
        # 检查是否已过期
        expiry_time = link_info.get('expiry_time')
        if expiry_time:
            try:
                # 解决时区问题
                # 使用 fromisoformat 解析 ISO 8601 UTC 字符串
                # Python < 3.11 doesn't handle Z directly, remove it.
                if expiry_time.endswith('Z'):
                    expiry_time_str = expiry_time[:-1] + '+00:00'
                else:
                    expiry_time_str = expiry_time
                
                expiry_datetime = datetime.fromisoformat(expiry_time_str)
                
                if expiry_datetime.tzinfo is None:
                     expiry_datetime = expiry_datetime.replace(tzinfo=timezone.utc)
                
                # 获取当前 UTC 时间进行比较
                if datetime.now(timezone.utc) > expiry_datetime:
                    data["message"] = "此外链已过期"
                    return render_template('exlink_error.html', message=data["message"])
            except (ValueError, TypeError) as e:
                # 解析失败，记录错误，并可能视为无效链接
                print(f"Error parsing expiry_time '{expiry_time}': {e}")
                data["message"] = "外链信息有误（无效的过期时间）"
                return render_template('exlink_error.html', message=data["message"]) 
                
        
        # 检查使用次数是否超过限制
        used_quota = link_info.get('used_quota', 0)
        total_quota = link_info.get('total_quota', 0)
        
        if used_quota < total_quota:
            # 不再自动增加使用次数，而是由扫码登录成功后增加
            # 获取关联的网盘信息
            drive_id = link_info.get('drive_id')
            drive_info = db.get_user_drive(drive_id)
            
            if drive_info:
                data["status"] = True
                data["drive_info"] = {
                    "provider_name": drive_info.get('provider_name'),
                    "login_config": drive_info.get('login_config')
                }
                data["message"] = "外链访问成功"
                data["remaining"] = total_quota - used_quota
                
                # 返回页面和网盘信息
                return render_template('exlink_view.html', 
                                      link_info=link_info, 
                                      drive_info=drive_info,
                                      remaining_count=total_quota - used_quota,
                                      expiry_time=link_info.get('expiry_time'))
            else:
                data["message"] = "找不到关联的网盘信息"
        else:
            data["message"] = "此外链已达到使用次数限制"
    else:
        data["message"] = "无效的外链ID"
    
    # 如果失败，返回错误页面
    return render_template('exlink_error.html', message=data["message"])


@app.route('/admin/')
def admin():
    db = get_db()
    providers = db.get_all_drive_providers()
    alluser_drives = db.get_all_user_drives()
    return render_template('admin.html',providers=providers,alluser_drives=alluser_drives)


@app.route('/admin/drive_provider/<metfunc>',methods=['POST'])
def drive_provider(metfunc):
    db = get_db()
    data = {"status":False}
    if metfunc == "get":
        
        alldrive= db.get_all_drive_providers()
        if len(alldrive) > 0:
            data["status"] = True
            data['data'] = alldrive
        # 使用jsonify确保中文正确显示
    elif metfunc == "add":
        """
        json样板
        body -- {
            "config_vars": {
                "data": {
                    "client_id": "532",
                    "kps_wg": "",
                    "request_id": "",
                    "sign_wg": "",
                    "token": "",
                    "v": "1.2",
                    "vcode": ""
                },
                "kps_wg": "",
                "redirect_uri": "https://uop.quark.cn/cas/ajax/loginWithKpsAndQrcodeToken",
                "sign_wg": ""
            },
            "provider_name": "夸克网盘",
            "remarks": "夸克网盘"
        }
        Return: status
        """
        
        body = request.get_json()
        status = db.add_drive_provider(body.get("provider_name","测试网盘"),body.get("config_vars"),body.get("remarks",""))
        
        if status:
            data["status"] = True
            data["data"] = body
    return data

@app.route('/admin/user_drive/<metfunc>',methods=['POST'])
def user_drive(metfunc):
    db = get_db()
    data = {"status":False}
    if metfunc == "get":
        body = request.get_json()
        # 如果提供了ID，则返回特定驱动的信息
        if body and 'id' in body:
            drive_id = body.get('id')
            user_drive = db.get_user_drive(drive_id)
            if user_drive:
                data["status"] = True
                data["data"] = user_drive
            else:
                data["status"] = False
                data["message"] = "未找到指定的网盘账号"
        # 如果提供了provider_name，则返回该类型的所有账号
        elif body and 'provider_name' in body:
            provider_name = body.get('provider_name')
            provider_drives = db.get_user_drives_by_provider(provider_name)
            data["status"] = True
            data["data"] = provider_drives if provider_drives else []
        else:
            # 否则返回所有驱动的信息
            alluser_drives = db.get_all_user_drives()
            # 即使列表为空也返回成功状态和空数组
            data["status"] = True
            data["data"] = alluser_drives if alluser_drives else []
    elif metfunc == "add":
        body = request.get_json()
        print(body)
        status = db.add_user_drive(body.get("provider_name","测试网盘"),body.get("login_config"),body.get("remarks",""))
        if status:
            data["status"] = True
            data["data"] = body
    elif metfunc == "update":
        body = request.get_json()
        print(body)
        print(body.get("id"),body.get("login_config"))
        status = db.update_user_drive(body.get("id"),json.loads(body.get("login_config")),body.get("remarks",""))
        if status:
            data["status"] = True
            data["data"] = body
    elif metfunc == "delete":
        body = request.get_json()
        drive_id = body.get("id")
        if drive_id:
            # 检查是否有关联的外链，如果有则不允许删除
            external_links = db.get_external_links_by_drive(drive_id)
            if external_links and len(external_links) > 0:
                data["status"] = False
                data["message"] = "该网盘账号有关联的外链，请先删除外链后再删除账号"
                return data
            
            status = db.delete_user_drive(drive_id)
            if status:
                data["status"] = True
                data["message"] = "网盘账号删除成功"
            else:
                data["message"] = "网盘账号删除失败，可能不存在"
        else:
            data["message"] = "缺少必要的ID参数"
    return data


class Exlink(MethodView):
    def demo(self):
        db = get_db()
        db.add_drive_provider(
            "阿里网盘",
            {
                "sign_wg": "",
                "kps_wg": "",
                "redirect_uri": "https://uop.quark.cn/cas/ajax/loginWithKpsAndQrcodeToken",
                "data":{
                    'client_id': '532',
                    'v': '1.2',
                    'request_id': "",
                    'sign_wg': "",
                    'kps_wg': "",
                    'vcode': "",
                    'token': ""
                }
            },
            "阿里网盘API配置"
        )
        return jsonify({"status": True, "message": "success"})
    
    def get(self):
        db = get_db()
        data = {"status": False}
        try:
            # 获取所有外链
            external_links = []
            results = db.cursor.execute("SELECT * FROM external_links").fetchall()
            for row in results:
                external_links.append(dict(row))
            
            data["status"] = True
            data["data"] = external_links
        except Exception as e:
            data["message"] = f"获取外链列表失败: {str(e)}"
        
        return jsonify(data)
    
    def post(self):
        """创建外链"""
        db = get_db()
        data = {"status": False}
        
        try:
            body = request.get_json()
            
            # 处理前端可能传递的两种数据格式
            # 1. 直接传递drive_id, total_quota, remarks
            # 2. 将这些参数封装在data字段中
            if body.get('data') and isinstance(body.get('data'), dict):
                # 如果参数被封装在data字段中，提取出来
                body_data = body.get('data')
                drive_id = body_data.get('account_id')  # 前端传的是account_id
                total_quota = float(body_data.get('total_quota', 1))
                remarks = body_data.get('remarks', '')
                expiry_time = body_data.get('expiry_time')
            else:
                # 直接从body中获取
                drive_id = body.get('drive_id')
                total_quota = float(body.get('total_quota', 1))
                remarks = body.get('remarks', '')
                expiry_time = body.get('expiry_time')
            
            if not drive_id:
                data["message"] = "缺少必要的drive_id参数"
                return jsonify(data)
                
            # 检查网盘是否存在
            user_drive = db.get_user_drive(drive_id)
            if not user_drive:
                data["message"] = "指定的网盘账号不存在"
                return jsonify(data)
                
            # 创建外链
            link_uuid = db.create_external_link(
                drive_id=drive_id,
                total_quota=total_quota,
                remarks=remarks,
                expiry_time=expiry_time
            )
            
            if link_uuid:
                data["status"] = True
                data["data"] = {
                    "link_uuid": link_uuid,
                    "url": f"/exlink/{link_uuid}"
                }
                data["message"] = "外链创建成功"
            else:
                data["message"] = "外链创建失败"
        except Exception as e:
            data["message"] = f"创建外链失败: {str(e)}"
        
        return jsonify(data)
    
    def delete(self):
        """删除外链"""
        db = get_db()
        data = {"status": False}
        
        try:
            body = request.get_json()
            link_uuid = body.get('link_uuid')
            
            if not link_uuid:
                data["message"] = "缺少必要的link_uuid参数"
                return jsonify(data)
                
            # 删除外链
            status = db.delete_external_link(link_uuid)
            
            if status:
                data["status"] = True
                data["message"] = "外链删除成功"
            else:
                data["message"] = "外链删除失败，可能不存在"
        except Exception as e:
            data["message"] = f"删除外链失败: {str(e)}"
        
        return jsonify(data)


app.add_url_rule('/admin/exlink', view_func=Exlink.as_view('exlink'))


# 添加新的URL规则 - 外链管理API
@app.route('/admin/exlink/get', methods=['POST'])
def get_external_links():
    return Exlink().get()


@app.route('/admin/exlink/create', methods=['POST'])
def create_external_link():
    return Exlink().post()


@app.route('/admin/exlink/delete', methods=['POST'])
def delete_external_link():
    return Exlink().delete()


# 新增：仪表盘数据 API
@app.route('/admin/dashboard_data', methods=['GET'])
def get_dashboard_data():
    db = get_db()
    try:
        user_drives_count = db.get_total_user_drives_count()
        active_links_count = db.get_active_external_links_count()
        # 使用外链总数作为"今日访问量"的简化替代
        total_links_count = db.get_total_external_links_count() 
        
        data = {
            "status": True,
            "data": {
                "user_drives_count": user_drives_count,
                "active_links_count": active_links_count,
                "total_links_count": total_links_count
            }
        }
    except Exception as e:
        print(f"获取仪表盘数据错误: {e}")
        data = {"status": False, "message": "获取仪表盘数据失败"}
    return jsonify(data)


# 新增：统计分析数据 API
@app.route('/admin/statistics_data', methods=['GET'])
def get_statistics_data():
    db = get_db()
    try:
        drives_by_provider = db.get_user_drives_count_by_provider()
        # 这里可以添加更多统计数据，例如外链访问趋势 (需要记录访问日志)
        # 暂时只返回网盘分布数据
        
        data = {
            "status": True,
            "data": {
                "drives_by_provider": drives_by_provider,
                # "access_trend": [] # 示例：将来可以添加访问趋势数据
            }
        }
    except Exception as e:
        print(f"获取统计数据错误: {e}")
        data = {"status": False, "message": "获取统计数据失败"}
    return jsonify(data)


# -----------------------------
#      应用程序运行入口
# -----------------------------
if __name__ == '__main__':
        # 启动Flask应用
    weburl = get_cnb_weburl(5000)
    print("Run_url:",weburl)
    app.config.from_pyfile("config.py")
    app.run(host="0.0.0.0")
    


    
