import os

class Config:
    # Secret key for sessions
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'kasir-pos-secret-key-2024'
    
    # Database configuration
    DB_HOST = 'localhost'
    DB_PORT = 3307
    DB_USER = 'root'
    DB_PASSWORD = ''
    DB_NAME = 'kasir_pos'
    
    # MySQL connection string
    MYSQL_HOST = DB_HOST
    MYSQL_PORT = DB_PORT
    MYSQL_USER = DB_USER
    MYSQL_PASSWORD = DB_PASSWORD
    MYSQL_DB = DB_NAME
    
    # Application settings
    ITEMS_PER_PAGE = 10
    LOW_STOCK_THRESHOLD = 10
    
    # Upload settings
    UPLOAD_FOLDER = 'static/uploads'
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max
    
    # Barcode scanner settings
    SCANNER_WIDTH = 640
    SCANNER_HEIGHT = 480

class DevelopmentConfig(Config):
    DEBUG = True

class ProductionConfig(Config):
    DEBUG = False

config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}
