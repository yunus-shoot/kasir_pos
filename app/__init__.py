from flask import Flask, session
from config import config
import mysql.connector
from mysql.connector import Error

def create_app(config_name='default'):
    app = Flask(__name__, template_folder='../templates', static_folder='../static')
    app.config.from_object(config[config_name])

    @app.template_filter('id_number')
    def format_indonesian_number(value):
        try:
            return f"{float(value or 0):,.0f}".replace(',', '.')
        except (TypeError, ValueError):
            return '0'
    
    # Initialize database
    init_database(app)
    
    # Register blueprints
    from app.routes import main_bp
    app.register_blueprint(main_bp)

    from app.utils import get_account_owner_id, get_store_settings

    @app.context_processor
    def inject_store_settings():
        user_id = session.get('user_id')
        if not user_id:
            return {}
        owner_id = get_account_owner_id(user_id)
        return {'current_store_settings': get_store_settings(owner_id)}
    
    return app

def get_db_connection():
    """Create and return a database connection"""
    try:
        connection = mysql.connector.connect(
            host='localhost',
            port=3307,
            user='root',
            password='',
            connection_timeout=5,
            database='kasir_pos'
        )
        return connection
    except Error as e:
        print(f"Error connecting to MySQL: {e}")
        return None

def ensure_id_primary_key(cursor, table_name):
    cursor.execute(f"SHOW INDEX FROM `{table_name}` WHERE Key_name = 'PRIMARY'")
    has_primary_key = cursor.fetchone() is not None
    cursor.execute(f"SHOW COLUMNS FROM `{table_name}` LIKE 'id'")
    id_column = cursor.fetchone()
    if id_column is None:
        raise RuntimeError(f"Cannot initialize {table_name}: id column is missing.")

    id_extra = id_column.get('Extra', '') if isinstance(id_column, dict) else id_column[5]
    if has_primary_key and 'auto_increment' in id_extra.lower():
        return

    cursor.execute(
        f"SELECT COUNT(*) AS row_count, COUNT(id) AS non_null_id_count, "
        f"COUNT(DISTINCT id) AS distinct_id_count FROM `{table_name}`"
    )
    counts = cursor.fetchone()
    if isinstance(counts, dict):
        row_count = counts['row_count']
        non_null_id_count = counts['non_null_id_count']
        distinct_id_count = counts['distinct_id_count']
    else:
        row_count, non_null_id_count, distinct_id_count = counts
    if row_count != non_null_id_count or row_count != distinct_id_count:
        raise RuntimeError(
            f"Cannot add the {table_name}.id primary key because existing IDs are null or duplicated."
        )

    alter_sql = f"ALTER TABLE `{table_name}` MODIFY id INT NOT NULL AUTO_INCREMENT"
    if not has_primary_key:
        alter_sql += ", ADD PRIMARY KEY (id)"
    cursor.execute(alter_sql)

def init_database(app):
    """Initialize database and create tables if not exist"""
    try:
        # First connect without database to create it
        connection = mysql.connector.connect(
            host='localhost',
            port=3307,
            user='root',
            password='',
            connection_timeout=5
        )
        cursor = connection.cursor()
        
        # Create database if not exists
        cursor.execute("CREATE DATABASE IF NOT EXISTS kasir_pos")
        cursor.close()
        connection.close()
        
        # Now connect to the database and create tables
        connection = mysql.connector.connect(
            host='localhost',
            port=3307,
            user='root',
            password='',
            connection_timeout=5,
            database='kasir_pos'
        )
        cursor = connection.cursor()
        
        # Create users table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INT AUTO_INCREMENT PRIMARY KEY,
                username VARCHAR(50) UNIQUE NOT NULL,
                password VARCHAR(255) NOT NULL,
                nama_lengkap VARCHAR(100) NOT NULL,
                role ENUM('admin', 'kasir') NOT NULL,
                owner_id INT DEFAULT NULL,
                profile_photo VARCHAR(255) DEFAULT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("SHOW COLUMNS FROM users LIKE 'role'")
        role_column = cursor.fetchone()
        role_type = role_column['Type'] if isinstance(role_column, dict) else role_column[1]
        if not all(f"'{role}'" in role_type for role in ('umkm', 'web_admin')):
            cursor.execute(
                "ALTER TABLE users MODIFY role ENUM('admin', 'kasir', 'umkm', 'web_admin') NOT NULL"
            )
        ensure_id_primary_key(cursor, 'users')
        cursor.execute("SHOW COLUMNS FROM users LIKE 'owner_id'")
        if cursor.fetchone() is None:
            cursor.execute("ALTER TABLE users ADD COLUMN owner_id INT DEFAULT NULL")
        cursor.execute("SHOW COLUMNS FROM users LIKE 'profile_photo'")
        if cursor.fetchone() is None:
            cursor.execute("ALTER TABLE users ADD COLUMN profile_photo VARCHAR(255) DEFAULT NULL")
        cursor.execute("UPDATE users SET owner_id = id WHERE role = 'admin' AND owner_id IS NULL")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS umkm_accounts (
                id INT AUTO_INCREMENT PRIMARY KEY,
                owner_id INT NOT NULL,
                account_code VARCHAR(20) NOT NULL,
                account_name VARCHAR(150) NOT NULL,
                account_type ENUM('aset', 'kewajiban', 'ekuitas', 'pendapatan', 'beban') NOT NULL,
                normal_balance ENUM('debit', 'kredit') NOT NULL,
                is_active TINYINT(1) NOT NULL DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE KEY uq_umkm_account_code (owner_id, account_code),
                INDEX idx_umkm_account_type (owner_id, account_type)
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS umkm_journals (
                id INT AUTO_INCREMENT PRIMARY KEY,
                owner_id INT NOT NULL,
                journal_date DATE NOT NULL,
                reference VARCHAR(50) DEFAULT NULL,
                description VARCHAR(255) NOT NULL,
                journal_type ENUM('saldo_awal', 'umum', 'penyesuaian') NOT NULL DEFAULT 'umum',
                cash_flow_category ENUM('operasional', 'investasi', 'pendanaan', 'nonkas') NOT NULL DEFAULT 'operasional',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_umkm_journal_owner_date (owner_id, journal_date, id)
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS umkm_journal_lines (
                id INT AUTO_INCREMENT PRIMARY KEY,
                journal_id INT NOT NULL,
                account_id INT NOT NULL,
                debit DECIMAL(15, 2) NOT NULL DEFAULT 0,
                credit DECIMAL(15, 2) NOT NULL DEFAULT 0,
                INDEX idx_umkm_line_account (account_id),
                CONSTRAINT fk_umkm_line_journal FOREIGN KEY (journal_id)
                    REFERENCES umkm_journals(id) ON DELETE CASCADE,
                CONSTRAINT fk_umkm_line_account FOREIGN KEY (account_id)
                    REFERENCES umkm_accounts(id)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS member (
                id INT AUTO_INCREMENT PRIMARY KEY,
                owner_id INT NOT NULL,
                nama VARCHAR(150) NOT NULL,
                telepon VARCHAR(30) NOT NULL,
                email VARCHAR(150) DEFAULT NULL,
                alamat TEXT,
                diskon_persen DECIMAL(5, 2) NOT NULL DEFAULT 0,
                aktif TINYINT(1) NOT NULL DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                INDEX idx_member_owner_nama (owner_id, nama),
                INDEX idx_member_owner_telepon (owner_id, telepon)
            )
        """)
        
        # Create kategori table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS kategori (
                id INT AUTO_INCREMENT PRIMARY KEY,
                nama_kategori VARCHAR(100) NOT NULL,
                deskripsi TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
            )
        """)
        ensure_id_primary_key(cursor, 'kategori')
        cursor.execute("SHOW COLUMNS FROM kategori LIKE 'user_id'")
        if cursor.fetchone() is None:
            cursor.execute("ALTER TABLE kategori ADD COLUMN user_id INT DEFAULT NULL")
        
        # Create barang table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS barang (
                id INT AUTO_INCREMENT PRIMARY KEY,
                kode_barang VARCHAR(50) UNIQUE NOT NULL,
                nama_barang VARCHAR(200) NOT NULL,
                kategori_id INT NOT NULL,
                harga_beli DECIMAL(12, 2) NOT NULL,
                harga_jual DECIMAL(12, 2) NOT NULL,
                stok INT DEFAULT 0,
                barcode VARCHAR(100),
                deskripsi TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                FOREIGN KEY (kategori_id) REFERENCES kategori(id)
            )
        """)
        ensure_id_primary_key(cursor, 'barang')
        cursor.execute("SHOW COLUMNS FROM barang LIKE 'user_id'")
        if cursor.fetchone() is None:
            cursor.execute("ALTER TABLE barang ADD COLUMN user_id INT DEFAULT NULL")

        # Product codes belong to each admin's catalog, not to the whole database.
        # Replace the old global unique index so two admins can use the same code.
        try:
            cursor.execute("ALTER TABLE barang DROP INDEX kode_barang")
        except Error:
            pass
        try:
            cursor.execute("ALTER TABLE barang ADD UNIQUE KEY uq_barang_user_kode (user_id, kode_barang)")
        except Error:
            pass
        cursor.execute("SHOW INDEX FROM barang WHERE Key_name = 'idx_barang_user_barcode'")
        if not cursor.fetchall():
            cursor.execute("ALTER TABLE barang ADD INDEX idx_barang_user_barcode (user_id, barcode)")
        
        # Create barcode_produk table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS barcode_produk (
                id INT AUTO_INCREMENT PRIMARY KEY,
                nama_barang VARCHAR(200) NOT NULL,
                kategori_id INT NOT NULL,
                harga_beli DECIMAL(12, 2) NOT NULL,
                harga_jual DECIMAL(12, 2) NOT NULL,
                stok INT DEFAULT 0,
                ean13 VARCHAR(13) UNIQUE NOT NULL,
                jumlah_label INT DEFAULT 1,
                deskripsi TEXT,
                user_id INT DEFAULT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                FOREIGN KEY (kategori_id) REFERENCES kategori(id),
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)
        cursor.execute("SHOW COLUMNS FROM barcode_produk LIKE 'stok'")
        if cursor.fetchone() is None:
            cursor.execute("ALTER TABLE barcode_produk ADD COLUMN stok INT DEFAULT 0")
        cursor.execute("SHOW COLUMNS FROM barcode_produk LIKE 'barang_id'")
        if cursor.fetchone() is None:
            cursor.execute("ALTER TABLE barcode_produk ADD COLUMN barang_id INT DEFAULT NULL")
        cursor.execute("SHOW INDEX FROM barcode_produk WHERE Key_name = 'idx_barcode_produk_barang'")
        if cursor.fetchone() is None:
            cursor.execute("ALTER TABLE barcode_produk ADD INDEX idx_barcode_produk_barang (barang_id)")
        try:
            cursor.execute("""
                ALTER TABLE barcode_produk
                ADD CONSTRAINT fk_barcode_produk_barang
                FOREIGN KEY (barang_id) REFERENCES barang(id) ON DELETE CASCADE
            """)
        except Error:
            pass
        cursor.execute("""
            UPDATE barcode_produk bp
            JOIN barang b
              ON (b.barcode = bp.ean13 OR b.kode_barang = bp.ean13)
             AND b.user_id <=> bp.user_id
            SET bp.barang_id = b.id
            WHERE bp.barang_id IS NULL
        """)
        
        # Create transaksi table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS transaksi (
                id INT AUTO_INCREMENT PRIMARY KEY,
                kode_transaksi VARCHAR(50) UNIQUE NOT NULL,
                user_id INT NOT NULL,
                total DECIMAL(12, 2) NOT NULL,
                metode_pembayaran ENUM('tunai', 'qris', 'transfer') NOT NULL,
                jumlah_bayar DECIMAL(12, 2) NOT NULL,
                kembalian DECIMAL(12, 2) NOT NULL,
                status ENUM('selesai', 'batal') DEFAULT 'selesai',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)
        cursor.execute("SHOW COLUMNS FROM transaksi LIKE 'nama_pelanggan'")
        if cursor.fetchone() is None:
            cursor.execute("ALTER TABLE transaksi ADD COLUMN nama_pelanggan VARCHAR(200) DEFAULT NULL")
        cursor.execute("SHOW COLUMNS FROM transaksi LIKE 'member_id'")
        if cursor.fetchone() is None:
            cursor.execute("ALTER TABLE transaksi ADD COLUMN member_id INT DEFAULT NULL")
        cursor.execute("SHOW COLUMNS FROM transaksi LIKE 'diskon_persen'")
        if cursor.fetchone() is None:
            cursor.execute("ALTER TABLE transaksi ADD COLUMN diskon_persen DECIMAL(5, 2) NOT NULL DEFAULT 0")
        cursor.execute("SHOW COLUMNS FROM transaksi LIKE 'diskon_nominal'")
        if cursor.fetchone() is None:
            cursor.execute("ALTER TABLE transaksi ADD COLUMN diskon_nominal DECIMAL(12, 2) NOT NULL DEFAULT 0")
        
        # Create detail_transaksi table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS detail_transaksi (
                id INT AUTO_INCREMENT PRIMARY KEY,
                transaksi_id INT NOT NULL,
                barang_id INT NOT NULL,
                harga_saat_transaksi DECIMAL(12, 2) NOT NULL,
                harga_modal_saat_transaksi DECIMAL(12, 2) DEFAULT NULL,
                jumlah INT NOT NULL,
                subtotal DECIMAL(12, 2) NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (transaksi_id) REFERENCES transaksi(id),
                FOREIGN KEY (barang_id) REFERENCES barang(id)
            )
        """)
        ensure_id_primary_key(cursor, 'detail_transaksi')
        cursor.execute("SHOW COLUMNS FROM detail_transaksi LIKE 'harga_modal_saat_transaksi'")
        if cursor.fetchone() is None:
            cursor.execute("ALTER TABLE detail_transaksi ADD COLUMN harga_modal_saat_transaksi DECIMAL(12, 2) DEFAULT NULL")
        
        # Check if admin exists, if not create default admin
        cursor.execute("SELECT COUNT(*) FROM users WHERE username = 'admin'")
        if cursor.fetchone()[0] == 0:
            cursor.execute("""
                INSERT INTO users (username, password, nama_lengkap, role)
                VALUES ('admin', 'admin123', 'Administrator', 'admin')
            """)
        cursor.execute("UPDATE users SET owner_id = id WHERE role = 'admin' AND owner_id IS NULL")
        cursor.execute("""
            INSERT INTO users (username, password, nama_lengkap, role)
            SELECT 'umkm', 'umkm123', 'Pembukuan UMKM', 'umkm'
            WHERE NOT EXISTS (SELECT 1 FROM users WHERE username = 'umkm')
        """)
        cursor.execute("UPDATE users SET owner_id = id WHERE username = 'umkm' AND role = 'umkm' AND owner_id IS NULL")
        cursor.execute("SELECT id FROM users WHERE username = 'umkm' AND role = 'umkm' LIMIT 1")
        umkm_user = cursor.fetchone()
        if umkm_user:
            from app.accounting import seed_chart_accounts
            seed_chart_accounts(umkm_user[0], cursor)
        else:
            cursor.execute("SELECT role FROM users WHERE username = 'umkm' LIMIT 1")
            conflicting_user = cursor.fetchone()
            if conflicting_user:
                cursor.close()
                connection.close()
                raise RuntimeError(
                    "The username 'umkm' is already assigned to a non-UMKM account. "
                    "Rename that account before creating the dedicated UMKM login."
                )

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                id INT AUTO_INCREMENT PRIMARY KEY,
                owner_id INT DEFAULT NULL,
                nama_toko VARCHAR(200) DEFAULT 'Kasir POS',
                alamat TEXT,
                telepon VARCHAR(50),
                email VARCHAR(100),
                notification_email VARCHAR(150) DEFAULT NULL,
                logo VARCHAR(255),
                footer_message VARCHAR(255) DEFAULT 'Terima kasih atas kunjungan Anda',
                low_stock_threshold INT DEFAULT 10,
                email_notification TINYINT(1) DEFAULT 0,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                UNIQUE KEY uq_settings_owner_id (owner_id)
            )
        """)
        ensure_id_primary_key(cursor, 'settings')
        settings_columns = {
            'owner_id': "INT DEFAULT NULL",
            'notification_email': "VARCHAR(150) DEFAULT NULL",
            'footer_message': "VARCHAR(255) DEFAULT 'Terima kasih atas kunjungan Anda'",
            'low_stock_threshold': "INT DEFAULT 10",
            'email_notification': "TINYINT(1) DEFAULT 0",
        }
        for column_name, column_definition in settings_columns.items():
            cursor.execute(f"SHOW COLUMNS FROM settings LIKE '{column_name}'")
            if cursor.fetchone() is None:
                cursor.execute(f"ALTER TABLE settings ADD COLUMN {column_name} {column_definition}")

        cursor.execute("SELECT id FROM users WHERE role = 'admin' ORDER BY id LIMIT 1")
        first_admin = cursor.fetchone()
        if first_admin:
            cursor.execute(
                "SELECT id FROM settings WHERE owner_id IS NULL ORDER BY id LIMIT 1"
            )
            legacy_settings = cursor.fetchone()
            if legacy_settings:
                cursor.execute(
                    "UPDATE settings SET owner_id = %s WHERE id = %s",
                    (first_admin[0], legacy_settings[0])
                )

        cursor.execute("SHOW INDEX FROM settings WHERE Key_name = 'uq_settings_owner_id'")
        if not cursor.fetchall():
            cursor.execute("ALTER TABLE settings ADD UNIQUE KEY uq_settings_owner_id (owner_id)")
        
        # Check if kategori exists, if not create default kategori
        cursor.execute("SELECT COUNT(*) FROM kategori")
        if cursor.fetchone()[0] == 0:
            cursor.execute("""
                INSERT INTO kategori (nama_kategori, deskripsi)
                VALUES 
                ('Makanan', 'Semua produk makanan'),
                ('Minuman', 'Semua produk minuman'),
                ('Barang Umum', 'Barang umum lainnya')
            """)
        
        connection.commit()
        cursor.close()
        connection.close()
        print("Database initialized successfully!")
        
    except Error as e:
        print(f"Error initializing database: {e}")
        raise
