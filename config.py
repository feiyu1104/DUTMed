"""
配置管理模块 - 集中管理所有配置项
"""
import os
from typing import Dict, Any
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()


class Config:
    """应用配置类"""
    
    # Neo4j 配置
    NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
    NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "123456789")
    
    # 阿里云通义千问 API 配置
    ALI_API_KEY = os.getenv("ALI_API_KEY")
    ALI_BASE_URL = os.getenv("ALI_BASE_URL", "https://dashscope.aliyuncs.com/api/v1")
    ALI_MODEL0 = os.getenv("ALI_MODEL0", "qwen-plus")  # 文本模型
    ALI_MODEL1 = os.getenv("ALI_MODEL1", "qwen-vl-plus")  # 视觉模型
    
    # Flask 配置
    FLASK_HOST = os.getenv("FLASK_HOST", "0.0.0.0")
    FLASK_PORT = int(os.getenv("FLASK_PORT", "5001"))
    FLASK_DEBUG = os.getenv("FLASK_DEBUG", "True").lower() == "true"
    
    # 文件上传配置
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'bmp', 'tiff'}
    UPLOAD_FOLDER = "static/uploads"
    SEGMENTED_FOLDER = "static/segmented"
    
    # FastSAM 模型配置
    FASTSAM_MODEL_PATH = "./weights/FastSAM_X.pt"
    
    # 缓存配置
    CACHE_ENABLED = os.getenv("CACHE_ENABLED", "True").lower() == "true"
    CACHE_TTL = int(os.getenv("CACHE_TTL", "3600"))  # 1小时
    CACHE_MAX_SIZE = int(os.getenv("CACHE_MAX_SIZE", "1000"))  # 最多缓存1000个条目
    
    # API 重试配置
    API_MAX_RETRIES = 3
    API_BASE_DELAY = 1.0
    API_TIMEOUT = 60
    
    # 速率限制配置
    RATE_LIMIT_ENABLED = os.getenv("RATE_LIMIT_ENABLED", "True").lower() == "true"
    RATE_LIMIT_PER_MINUTE = int(os.getenv("RATE_LIMIT_PER_MINUTE", "60"))
    
    @classmethod
    def validate(cls):
        """验证必需的配置项"""
        errors = []
        
        if not cls.ALI_API_KEY:
            errors.append("ALI_API_KEY 未设置")
        
        if not cls.NEO4J_URI:
            errors.append("NEO4J_URI 未设置")
        
        if not cls.NEO4J_USER:
            errors.append("NEO4J_USER 未设置")
            
        if not cls.NEO4J_PASSWORD:
            errors.append("NEO4J_PASSWORD 未设置")
        
        if errors:
            raise EnvironmentError(
                f"配置验证失败:\n" + "\n".join(f"  - {e}" for e in errors)
            )
        
        return True
    
    @classmethod
    def get_neo4j_config(cls) -> Dict[str, str]:
        """获取Neo4j配置"""
        return {
            "uri": cls.NEO4J_URI,
            "user": cls.NEO4J_USER,
            "password": cls.NEO4J_PASSWORD
        }
    
    @classmethod
    def get_ali_config(cls) -> Dict[str, str]:
        """获取阿里云API配置"""
        return {
            "api_key": cls.ALI_API_KEY,
            "base_url": cls.ALI_BASE_URL,
            "model0": cls.ALI_MODEL0,
            "model1": cls.ALI_MODEL1
        }
    
    @classmethod
    def to_dict(cls) -> Dict[str, Any]:
        """转换为字典（用于调试，不包含敏感信息）"""
        return {
            "neo4j_uri": cls.NEO4J_URI,
            "neo4j_user": cls.NEO4J_USER,
            "ali_base_url": cls.ALI_BASE_URL,
            "ali_model0": cls.ALI_MODEL0,
            "ali_model1": cls.ALI_MODEL1,
            "flask_host": cls.FLASK_HOST,
            "flask_port": cls.FLASK_PORT,
            "cache_enabled": cls.CACHE_ENABLED,
            "cache_ttl": cls.CACHE_TTL,
            "rate_limit_enabled": cls.RATE_LIMIT_ENABLED,
        }


# 在模块导入时验证配置
try:
    Config.validate()
except EnvironmentError as e:
    # 只在非测试环境中抛出错误
    if os.getenv("TESTING") != "true":
        print(f"警告: {e}")
        print("请创建 .env 文件并设置必需的环境变量")
