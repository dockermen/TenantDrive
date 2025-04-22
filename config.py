"""
应用配置文件
"""

# Flask配置
SECRET_KEY = 'replace-with-your-secure-key'
DEBUG = True
TEMPLATES_AUTO_RELOAD= True

# 应用配置
DEFAULT_EXPIRY_HOURS = 24  # 外链默认过期时间（小时）
MAX_QUOTA_PER_LINK = 100   # 每个外链的最大使用次数

# 日志配置
LOG_LEVEL = 'INFO'
LOG_FILE = 'logs/app.log'
LOG_MAX_SIZE = 10240    # 日志文件最大大小（字节）
LOG_BACKUP_COUNT = 10   # 日志备份文件数量

#数据库
DATABASE = 'database.db'