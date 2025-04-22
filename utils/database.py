import sqlite3
import json
import uuid
from typing import Dict, Any, Optional
from datetime import datetime, timedelta


class CloudDriveDatabase:
    """网盘数据库管理类"""
    
    def __init__(self, db_path: str = "cloud_drive.db"):
        """
        初始化数据库连接
        
        参数:
            db_path: 数据库文件路径
        """
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self.cursor = self.conn.cursor()
        self._create_tables()
        
    def _create_tables(self):
        """创建所需的数据库表并确保表结构是最新的"""
        # 1. 网盘驱动表
        self.cursor.execute('''
        CREATE TABLE IF NOT EXISTS drive_providers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            provider_name TEXT UNIQUE NOT NULL,
            config_vars TEXT NOT NULL,
            remarks TEXT
        )
        ''')
        
        # 2. 用户网盘表
        self.cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_drives (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            provider_name TEXT NOT NULL,
            login_config TEXT NOT NULL,
            remarks TEXT,
            FOREIGN KEY (provider_name) REFERENCES drive_providers (provider_name)
        )
        ''')
        
        # 3. 外链表
        self.cursor.execute('''
        CREATE TABLE IF NOT EXISTS external_links (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            drive_id INTEGER NOT NULL,
            total_quota REAL NOT NULL,
            used_quota REAL NOT NULL DEFAULT 0,
            link_uuid TEXT UNIQUE NOT NULL,
            remarks TEXT,
            FOREIGN KEY (drive_id) REFERENCES user_drives (id)
        )
        ''')
        
        # 检查并添加expiry_time列到external_links表
        self._add_column_if_not_exists('external_links', 'expiry_time', 'TEXT')
        
        self.conn.commit()
    
    def _add_column_if_not_exists(self, table_name: str, column_name: str, column_type: str):
        """
        检查表是否存在指定列，如果不存在则添加
        
        参数:
            table_name: 表名
            column_name: 列名
            column_type: 列类型
        """
        self.cursor.execute(f"PRAGMA table_info({table_name})")
        columns = [column[1] for column in self.cursor.fetchall()]
        if column_name not in columns:
            try:
                self.cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}")
                self.conn.commit()
                print(f"已成功添加列 '{column_name}' 到表 '{table_name}'")
            except sqlite3.OperationalError as e:
                print(f"添加列 '{column_name}' 到表 '{table_name}' 时出错: {e}")
    
    # 网盘驱动表操作
    def add_drive_provider(self, provider_name: str, config_vars: Dict[str, Any], remarks: Optional[str] = None) -> bool:
        """
        添加网盘服务商
        
        参数:
            provider_name: 服务商名称
            config_vars: 配置参数
            remarks: 备注说明
            
        返回:
            bool: 是否添加成功
        """
        try:
            self.cursor.execute(
                "INSERT INTO drive_providers (provider_name, config_vars, remarks) VALUES (?, ?, ?)",
                (provider_name, json.dumps(config_vars, ensure_ascii=False), remarks)
            )
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            # 服务商名称已存在
            return False
    
    def get_drive_provider(self, provider_name: str) -> Optional[Dict[str, Any]]:
        """
        获取网盘服务商信息
        
        参数:
            provider_name: 服务商名称
            
        返回:
            Dict: 服务商信息，不存在时返回None
        """
        self.cursor.execute("SELECT * FROM drive_providers WHERE provider_name = ?", (provider_name,))
        result = self.cursor.fetchone()
        if result:
            result_dict = dict(result)
            result_dict['config_vars'] = json.loads(result_dict['config_vars'])
            return result_dict
        return None
    
    def get_all_drive_providers(self) -> list:
        """
        获取所有网盘服务商
        
        返回:
            List: 所有服务商信息列表
        """
        self.cursor.execute("SELECT * FROM drive_providers")
        results = self.cursor.fetchall()
        providers = []
        for row in results:
            provider = dict(row)
            provider['config_vars'] = json.loads(provider['config_vars'])
            providers.append(provider)
        return providers
    
    def update_drive_provider(self, provider_name: str, config_vars: Dict[str, Any] = None, remarks: str = None) -> bool:
        """
        更新网盘服务商信息
        
        参数:
            provider_name: 服务商名称
            config_vars: 配置参数，可选
            remarks: 备注说明，可选
            
        返回:
            bool: 是否更新成功
        """
        try:
            current = self.get_drive_provider(provider_name)
            if not current:
                return False
                
            if config_vars is not None:
                config_vars_json = json.dumps(config_vars, ensure_ascii=False)
            else:
                config_vars_json = json.dumps(current['config_vars'], ensure_ascii=False)
                
            if remarks is None:
                remarks = current['remarks']
                
            self.cursor.execute(
                "UPDATE drive_providers SET config_vars = ?, remarks = ? WHERE provider_name = ?",
                (config_vars_json, remarks, provider_name)
            )
            self.conn.commit()
            return True
        except Exception:
            return False
    
    def delete_drive_provider(self, provider_name: str) -> bool:
        """
        删除网盘服务商
        
        参数:
            provider_name: 服务商名称
            
        返回:
            bool: 是否删除成功
        """
        try:
            self.cursor.execute("DELETE FROM drive_providers WHERE provider_name = ?", (provider_name,))
            self.conn.commit()
            return self.cursor.rowcount > 0
        except Exception:
            return False
    
    # 用户网盘表操作
    def add_user_drive(self, provider_name: str, login_config: Dict[str, Any], remarks: Optional[str] = None) -> Optional[int]:
        """
        添加用户网盘
        
        参数:
            provider_name: 服务商名称
            login_config: 登录配置
            remarks: 备注说明
            
        返回:
            int: 新添加的用户网盘ID，失败时返回None
        """
        try:
            # 检查服务商是否存在
            if not self.get_drive_provider(provider_name):
                return None
                
            self.cursor.execute(
                "INSERT INTO user_drives (provider_name, login_config, remarks) VALUES (?, ?, ?)",
                (provider_name, json.dumps(login_config, ensure_ascii=False), remarks)
            )
            self.conn.commit()
            return self.cursor.lastrowid
        except Exception:
            return None
    
    def get_user_drive(self, drive_id: int) -> Optional[Dict[str, Any]]:
        """
        获取用户网盘信息
        
        参数:
            drive_id: 网盘ID
            
        返回:
            Dict: 用户网盘信息，不存在时返回None
        """
        self.cursor.execute("SELECT * FROM user_drives WHERE id = ?", (drive_id,))
        result = self.cursor.fetchone()
        if result:
            result_dict = dict(result)
            result_dict['login_config'] = json.loads(result_dict['login_config'])
            return result_dict
        return None
    
    def get_user_drives_by_provider(self, provider_name: str) -> list:
        """
        获取指定服务商的所有用户网盘
        
        参数:
            provider_name: 服务商名称
            
        返回:
            List: 用户网盘信息列表
        """
        self.cursor.execute("SELECT * FROM user_drives WHERE provider_name = ?", (provider_name,))
        results = self.cursor.fetchall()
        drives = []
        for row in results:
            drive = dict(row)
            drive['login_config'] = json.loads(drive['login_config'])
            drives.append(drive)
        return drives
    
    def get_all_user_drives(self) -> list:
        """
        获取所有用户网盘
        
        返回:
            List: 所有用户网盘信息列表
        """
        self.cursor.execute("SELECT * FROM user_drives")
        results = self.cursor.fetchall()
        drives = []
        for row in results:
            drive = dict(row)
            drive['login_config'] = json.loads(drive['login_config'])
            drives.append(drive)
        return drives
    
    def update_user_drive(self, drive_id: int, login_config: Dict[str, Any] = None, remarks: str = None) -> bool:
        """
        更新用户网盘信息
        
        参数:
            drive_id: 网盘ID
            login_config: 登录配置，可选
            remarks: 备注说明，可选
            
        返回:
            bool: 是否更新成功
        """
        try:
            current = self.get_user_drive(drive_id)
            if not current:
                return False
                
            if login_config is not None:
                login_config_json = json.dumps(login_config, ensure_ascii=False)
            else:
                login_config_json = json.dumps(current['login_config'], ensure_ascii=False)
                
            if remarks is None:
                remarks = current['remarks']
                
            self.cursor.execute(
                "UPDATE user_drives SET login_config = ?, remarks = ? WHERE id = ?",
                (login_config_json, remarks, drive_id)
            )
            self.conn.commit()
            return True
        except Exception:
            return False
    
    def delete_user_drive(self, drive_id: int) -> bool:
        """
        删除用户网盘
        
        参数:
            drive_id: 网盘ID
            
        返回:
            bool: 是否删除成功
        """
        try:
            self.cursor.execute("DELETE FROM user_drives WHERE id = ?", (drive_id,))
            self.conn.commit()
            return self.cursor.rowcount > 0
        except Exception:
            return False
    
    # 外链表操作
    def create_external_link(self, drive_id: int, total_quota: float, remarks: Optional[str] = None, expiry_time: str = None) -> Optional[str]:
        """
        创建外链
        
        参数:
            drive_id: 网盘ID
            total_quota: 总配额（使用次数）
            remarks: 备注说明
            expiry_time: 过期时间，格式为ISO 8601
            
        返回:
            str: 外链UUID，失败时返回None
        """
        try:
            # 检查用户网盘是否存在
            if not self.get_user_drive(drive_id):
                return None
                
            # 生成不重复的UUID
            link_uuid = str(uuid.uuid4())
            while self.get_external_link_by_uuid(link_uuid):
                link_uuid = str(uuid.uuid4())
            
            # 如果没有指定到期时间，默认为24小时后
            if not expiry_time:
                expiry_time = (datetime.now() + timedelta(hours=24)).isoformat()
                
            self.cursor.execute(
                "INSERT INTO external_links (drive_id, total_quota, used_quota, link_uuid, remarks, expiry_time) VALUES (?, ?, 0, ?, ?, ?)",
                (drive_id, total_quota, link_uuid, remarks, expiry_time)
            )
            self.conn.commit()
            return link_uuid
        except Exception as e:
            print(f"创建外链错误: {e}")
            return None
    
    def get_external_link(self, link_id: int) -> Optional[Dict[str, Any]]:
        """
        获取外链信息
        
        参数:
            link_id: 外链ID
            
        返回:
            Dict: 外链信息，不存在时返回None
        """
        self.cursor.execute("SELECT * FROM external_links WHERE id = ?", (link_id,))
        result = self.cursor.fetchone()
        if result:
            return dict(result)
        return None
    
    def get_external_link_by_uuid(self, link_uuid: str) -> Optional[Dict[str, Any]]:
        """
        通过UUID获取外链信息
        
        参数:
            link_uuid: 外链UUID
            
        返回:
            Dict: 外链信息，不存在时返回None
        """
        self.cursor.execute("SELECT * FROM external_links WHERE link_uuid = ?", (link_uuid,))
        result = self.cursor.fetchone()
        if result:
            return dict(result)
        return None
    
    def get_external_links_by_drive(self, drive_id: int) -> list:
        """
        获取指定用户网盘的所有外链
        
        参数:
            drive_id: 网盘ID
            
        返回:
            List: 外链信息列表
        """
        self.cursor.execute("SELECT * FROM external_links WHERE drive_id = ?", (drive_id,))
        return [dict(row) for row in self.cursor.fetchall()]
    
    def update_external_link_quota(self, link_uuid: str, used_quota: float) -> bool:
        """
        更新外链已使用配额
        
        参数:
            link_uuid: 外链UUID
            used_quota: 已使用配额
            
        返回:
            bool: 是否更新成功
        """
        try:
            link = self.get_external_link_by_uuid(link_uuid)
            if not link:
                return False
                
            # 确保不超过总配额
            if used_quota > link['total_quota']:
                return False
                
            self.cursor.execute(
                "UPDATE external_links SET used_quota = ? WHERE link_uuid = ?",
                (used_quota, link_uuid)
            )
            self.conn.commit()
            return True
        except Exception:
            return False
    
    def update_external_link(self, link_uuid: str, total_quota: float = None, remarks: str = None) -> bool:
        """
        更新外链信息
        
        参数:
            link_uuid: 外链UUID
            total_quota: 总配额，可选
            remarks: 备注说明，可选
            
        返回:
            bool: 是否更新成功
        """
        try:
            link = self.get_external_link_by_uuid(link_uuid)
            if not link:
                return False
                
            if total_quota is None:
                total_quota = link['total_quota']
                
            if remarks is None:
                remarks = link['remarks']
                
            # 确保新的总配额不小于已使用配额
            if total_quota < link['used_quota']:
                return False
                
            self.cursor.execute(
                "UPDATE external_links SET total_quota = ?, remarks = ? WHERE link_uuid = ?",
                (total_quota, remarks, link_uuid)
            )
            self.conn.commit()
            return True
        except Exception:
            return False
    
    def delete_external_link(self, link_uuid: str) -> bool:
        """
        删除外链
        
        参数:
            link_uuid: 外链UUID
            
        返回:
            bool: 是否删除成功
        """
        try:
            self.cursor.execute("DELETE FROM external_links WHERE link_uuid = ?", (link_uuid,))
            self.conn.commit()
            return self.cursor.rowcount > 0
        except Exception:
            return False
    
    def get_total_user_drives_count(self) -> int:
        """
        获取用户网盘总数
        
        返回:
            int: 用户网盘总数
        """
        try:
            self.cursor.execute("SELECT COUNT(*) FROM user_drives")
            result = self.cursor.fetchone()
            return result[0] if result else 0
        except Exception as e:
            print(f"获取用户网盘总数错误: {e}")
            return 0
    
    def get_active_external_links_count(self) -> int:
        """
        获取活跃外链数量
        
        返回:
            int: 活跃外链数量
        """
        try:
            # 获取当前时间的ISO格式
            now = datetime.now().isoformat()
            
            # 查询未过期且使用次数未达到上限的外链
            self.cursor.execute(
                "SELECT COUNT(*) FROM external_links WHERE (expiry_time IS NULL OR expiry_time > ?) AND used_quota < total_quota",
                (now,)
            )
            result = self.cursor.fetchone()
            return result[0] if result else 0
        except Exception as e:
            print(f"获取活跃外链数量错误: {e}")
            return 0  # 返回0或其他错误指示

    def get_total_external_links_count(self) -> int:
        """
        获取外链总数
        
        返回:
            int: 外链总数
        """
        try:
            self.cursor.execute("SELECT COUNT(*) FROM external_links")
            result = self.cursor.fetchone()
            return result[0] if result else 0
        except Exception as e:
            print(f"获取外链总数错误: {e}")
            return 0

    def get_user_drives_count_by_provider(self) -> Dict[str, int]:
        """
        按提供商统计用户网盘数量
        
        返回:
            Dict: 按提供商分类的网盘数量
        """
        try:
            self.cursor.execute("SELECT provider_name, COUNT(*) as count FROM user_drives GROUP BY provider_name")
            results = self.cursor.fetchall()
            return {row['provider_name']: row['count'] for row in results}
        except Exception as e:
            print(f"按提供商统计用户网盘数量错误: {e}")
            return {}
            
    def close(self):
        """关闭数据库连接"""
        if self.conn:
            self.conn.close() 