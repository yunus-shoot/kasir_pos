"""Utility functions for Kasir POS application"""
import re
from mysql.connector import Error
from app import get_db_connection
from datetime import datetime, timedelta


def parse_indonesian_number(value):
    """Parse Indonesian grouped numbers (1.234,50) and standard decimals (1234.50)."""
    if isinstance(value, bool):
        raise ValueError('Boolean is not a valid number.')
    if isinstance(value, (int, float)):
        return float(value)

    number = str(value or '').strip()
    if not number:
        raise ValueError('Number is empty.')

    number = number.replace(' ', '').replace('Rp', '').replace('IDR', '').replace('idr', '')
    number = number.replace('−', '-').replace('–', '-')
    number = re.sub(r'[^0-9,\.\-]', '', number)

    if not number or number in {'-', '.', ',', '-.', '-,'}:
        raise ValueError('Number is empty or invalid.')

    negative = number.startswith('-')
    number = number.replace('-', '')

    if ',' in number and '.' in number:
        if number.rfind(',') > number.rfind('.'):
            number = number.replace('.', '').replace(',', '.')
        else:
            number = number.replace(',', '')
    elif ',' in number:
        if number.count(',') > 1:
            if len(number.rsplit(',', 1)[1]) == 3:
                number = number.replace(',', '')
            else:
                number = number.replace(',', '.')
        else:
            number = number.replace(',', '.')
    elif '.' in number:
        last_group = number.rsplit('.', 1)[1]
        if len(last_group) == 3:
            number = number.replace('.', '')
    
    if '.' in number and number.count('.') == 1 and len(number.rsplit('.', 1)[1]) == 3:
        number = number.replace('.', '')

    result = float(number)
    return -result if negative else result


def get_all_barang(user_id=None):
    """Get all items from barang table for a specific admin"""
    connection = get_db_connection()
    barang_list = []
    
    if connection:
        cursor = connection.cursor(dictionary=True)
        if user_id is not None:
            cursor.execute("""
                SELECT b.*, k.nama_kategori 
                FROM barang b 
                LEFT JOIN kategori k ON b.kategori_id = k.id 
                WHERE b.user_id = %s
                ORDER BY b.nama_barang
            """, (user_id,))
        else:
            cursor.execute("""
                SELECT b.*, k.nama_kategori 
                FROM barang b 
                LEFT JOIN kategori k ON b.kategori_id = k.id 
                ORDER BY b.nama_barang
            """)
        barang_list = cursor.fetchall()
        cursor.close()
        connection.close()
    
    return barang_list

def get_barang_by_id(barang_id, user_id=None):
    """Get barang by ID"""
    connection = get_db_connection()
    barang = None
    
    if connection:
        cursor = connection.cursor(dictionary=True)
        if user_id is not None:
            cursor.execute("SELECT * FROM barang WHERE id = %s AND user_id = %s", (barang_id, user_id))
        else:
            cursor.execute("SELECT * FROM barang WHERE id = %s", (barang_id,))
        barang = cursor.fetchone()
        cursor.close()
        connection.close()
    
    return barang


def add_barang(kode_barang, nama_barang, kategori_id, harga_beli, harga_jual, stok, barcode, deskripsi, user_id=None):
    """Add new barang"""
    try:
        connection = get_db_connection()
        if connection:
            cursor = connection.cursor()
            cursor.execute("""
                INSERT INTO barang (kode_barang, nama_barang, kategori_id, harga_beli, harga_jual, stok, barcode, deskripsi, user_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (kode_barang, nama_barang, kategori_id, harga_beli, harga_jual, stok, barcode, deskripsi, user_id))
            connection.commit()
            cursor.close()
            connection.close()
            return True
    except Error as e:
        print(f"Error adding barang: {e}")
        return False
    
    return False

def update_barang(barang_id, kode_barang, nama_barang, kategori_id, harga_beli, harga_jual, stok, barcode, deskripsi, user_id=None):
    """Update barang"""
    try:
        connection = get_db_connection()
        if connection:
            cursor = connection.cursor()
            if user_id is not None:
                cursor.execute("""
                    UPDATE barang 
                    SET kode_barang=%s, nama_barang=%s, kategori_id=%s, harga_beli=%s, harga_jual=%s, stok=%s, barcode=%s, deskripsi=%s
                    WHERE id=%s AND user_id=%s
                """, (kode_barang, nama_barang, kategori_id, harga_beli, harga_jual, stok, barcode, deskripsi, barang_id, user_id))
            else:
                cursor.execute("""
                    UPDATE barang 
                    SET kode_barang=%s, nama_barang=%s, kategori_id=%s, harga_beli=%s, harga_jual=%s, stok=%s, barcode=%s, deskripsi=%s
                    WHERE id=%s
                """, (kode_barang, nama_barang, kategori_id, harga_beli, harga_jual, stok, barcode, deskripsi, barang_id))
            connection.commit()
            cursor.close()
            connection.close()
            return True
    except Error as e:
        print(f"Error updating barang: {e}")
        return False
    
    return False

def delete_barang(barang_id, user_id=None):
    """Delete barang"""
    try:
        connection = get_db_connection()
        if connection:
            cursor = connection.cursor()
            if user_id is not None:
                cursor.execute("DELETE FROM barang WHERE id = %s AND user_id = %s", (barang_id, user_id))
            else:
                cursor.execute("DELETE FROM barang WHERE id = %s", (barang_id,))
            connection.commit()
            cursor.close()
            connection.close()
            return True
    except Error as e:
        print(f"Error deleting barang: {e}")
        return False
    
    return False


def barang_has_related_transactions(barang_id):
    """Return True if barang is referenced by detail_transaksi."""
    connection = get_db_connection()
    if not connection:
        return False

    try:
        cursor = connection.cursor()
        cursor.execute("SELECT COUNT(*) FROM detail_transaksi WHERE barang_id = %s", (barang_id,))
        result = cursor.fetchone()
        cursor.close()
        connection.close()
        return result and result[0] > 0
    except Error as e:
        print(f"Error checking related transaksi for barang: {e}")
        return False


def sync_barcode_to_barang(ean13, nama_barang, kategori_id, harga_beli, harga_jual, stok, deskripsi, user_id=None):
    """Sync barcode product into barang inventory for scan support."""
    try:
        connection = get_db_connection()
        if connection:
            cursor = connection.cursor(dictionary=True)
            if user_id is not None:
                cursor.execute("""
                    SELECT id, stok
                    FROM barang
                    WHERE (barcode = %s OR kode_barang = %s)
                      AND user_id = %s
                """, (ean13, ean13, user_id))
            else:
                cursor.execute("""
                    SELECT id, stok
                    FROM barang
                    WHERE barcode = %s OR kode_barang = %s
                """, (ean13, ean13))

            existing = cursor.fetchone()

            if not existing:
                cursor.close()
                connection.close()
                return False

            cursor.execute("""
                UPDATE barang
                SET nama_barang=%s,
                    kategori_id=%s,
                    harga_beli=%s,
                    harga_jual=%s,
                    stok=%s,
                    barcode=%s,
                    deskripsi=%s
                WHERE id=%s
            """, (nama_barang, kategori_id, harga_beli, harga_jual, stok, ean13, deskripsi, existing['id']))

            connection.commit()
            cursor.close()
            connection.close()
            return True
    except Error as e:
        print(f"Error syncing barcode to barang: {e}")
        return False

    return False


def generate_unique_ean13(user_id=None):
    """Generate a unique EAN-13 code."""
    def calculate_check_digit(code12):
        total = 0
        for i, digit in enumerate(reversed(code12)):
            n = int(digit)
            total += n * (3 if i % 2 == 0 else 1)
        remainder = total % 10
        return str((10 - remainder) % 10)

    connection = get_db_connection()
    if not connection:
        return None

    import time, random
    base_prefix = str(user_id or 0).zfill(2)
    attempts = 0

    while attempts < 20:
        timestamp_part = str(int(time.time() * 1000))[-8:]
        random_part = ''.join(str(random.randint(0, 9)) for _ in range(2))
        code12 = (base_prefix + timestamp_part + random_part)[0:12]
        ean13 = code12 + calculate_check_digit(code12)

        cursor = connection.cursor()
        cursor.execute("SELECT id FROM barcode_produk WHERE ean13 = %s", (ean13,))
        existing = cursor.fetchone()
        if existing is None:
            cursor.execute("SELECT id FROM barang WHERE barcode = %s OR kode_barang = %s", (ean13, ean13))
            if cursor.fetchone() is None:
                cursor.close()
                connection.close()
                return ean13
        cursor.close()
        attempts += 1

    connection.close()
    return None


def get_all_kategori(user_id=None):
    """Get all categories for a specific admin"""
    connection = get_db_connection()
    kategori_list = []
    
    if connection:
        cursor = connection.cursor(dictionary=True)
        if user_id is not None:
            cursor.execute("SELECT * FROM kategori WHERE user_id = %s OR user_id IS NULL ORDER BY nama_kategori", (user_id,))
        else:
            cursor.execute("SELECT * FROM kategori ORDER BY nama_kategori")
        kategori_list = cursor.fetchall()
        cursor.close()
        connection.close()
    
    return kategori_list


def get_all_barcode_produk(user_id=None, search_query=None):
    """Get barcode product list for a specific admin with optional search."""
    connection = get_db_connection()
    barcode_list = []

    if connection:
        cursor = connection.cursor(dictionary=True)
        query = """
            SELECT bp.id, bp.barang_id, bp.ean13, bp.jumlah_label, bp.user_id,
                   bp.created_at, bp.updated_at,
                   COALESCE(b.nama_barang, bp.nama_barang) AS nama_barang,
                   COALESCE(b.kategori_id, bp.kategori_id) AS kategori_id,
                   COALESCE(b.harga_beli, bp.harga_beli) AS harga_beli,
                   COALESCE(b.harga_jual, bp.harga_jual) AS harga_jual,
                   COALESCE(b.stok, bp.stok) AS stok,
                   COALESCE(b.deskripsi, bp.deskripsi) AS deskripsi,
                   k.nama_kategori, b.kode_barang
            FROM barcode_produk bp
            LEFT JOIN barang b ON b.id = bp.barang_id
            LEFT JOIN kategori k ON k.id = COALESCE(b.kategori_id, bp.kategori_id)
        """
        conditions = []
        params = []
        if user_id is not None:
            conditions.append('bp.user_id = %s')
            params.append(user_id)
        if search_query:
            search_text = f"%{search_query}%"
            conditions.append("(COALESCE(b.nama_barang, bp.nama_barang) LIKE %s OR bp.ean13 LIKE %s OR b.kode_barang LIKE %s)")
            params.extend((search_text, search_text, search_text))
        if conditions:
            query += ' WHERE ' + ' AND '.join(conditions)
        query += ' ORDER BY bp.created_at DESC'
        cursor.execute(query, params)
        barcode_list = cursor.fetchall()
        cursor.close()
        connection.close()

    return barcode_list


def get_barcode_produk_by_id(barcode_id, user_id=None):
    """Get barcode product by ID."""
    connection = get_db_connection()
    barcode = None
    if connection:
        cursor = connection.cursor(dictionary=True)
        query = """
            SELECT bp.id, bp.barang_id, bp.ean13, bp.jumlah_label, bp.user_id,
                   bp.created_at, bp.updated_at,
                   COALESCE(b.nama_barang, bp.nama_barang) AS nama_barang,
                   COALESCE(b.kategori_id, bp.kategori_id) AS kategori_id,
                   COALESCE(b.harga_beli, bp.harga_beli) AS harga_beli,
                   COALESCE(b.harga_jual, bp.harga_jual) AS harga_jual,
                   COALESCE(b.stok, bp.stok) AS stok,
                   COALESCE(b.deskripsi, bp.deskripsi) AS deskripsi,
                   k.nama_kategori, b.kode_barang
            FROM barcode_produk bp
            LEFT JOIN barang b ON b.id = bp.barang_id
            LEFT JOIN kategori k ON k.id = COALESCE(b.kategori_id, bp.kategori_id)
            WHERE bp.id = %s
        """
        if user_id is not None:
            query += ' AND bp.user_id = %s'
            cursor.execute(query, (barcode_id, user_id))
        else:
            cursor.execute(query, (barcode_id,))
        barcode = cursor.fetchone()
        cursor.close()
        connection.close()
    return barcode


def add_barcode_produk(nama_barang, kategori_id, harga_beli, harga_jual, stok=0, jumlah_label=1, deskripsi=None, user_id=None):
    """Create a product and its barcode record atomically."""
    ean13 = generate_unique_ean13(user_id)
    if not ean13:
        return False

    connection = None
    cursor = None
    try:
        connection = get_db_connection()
        if not connection:
            return False

        cursor = connection.cursor(dictionary=True)
        if user_id is not None:
            cursor.execute("SELECT id FROM kategori WHERE id = %s AND (user_id = %s OR user_id IS NULL)", (kategori_id, user_id))
        else:
            cursor.execute("SELECT id FROM kategori WHERE id = %s", (kategori_id,))
        if not cursor.fetchone():
            connection.rollback()
            return False

        cursor.execute("""
            INSERT INTO barang
                (kode_barang, nama_barang, kategori_id, harga_beli, harga_jual,
                 stok, barcode, deskripsi, user_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (ean13, nama_barang, kategori_id, harga_beli, harga_jual, stok, ean13, deskripsi, user_id))
        barang_id = cursor.lastrowid

        cursor.execute("""
            INSERT INTO barcode_produk
                (barang_id, nama_barang, kategori_id, harga_beli, harga_jual, stok,
                 ean13, jumlah_label, deskripsi, user_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            barang_id, nama_barang, kategori_id, harga_beli, harga_jual, stok,
            ean13, jumlah_label, deskripsi, user_id
        ))
        connection.commit()
        return ean13
    except Error as e:
        if connection:
            connection.rollback()
        print(f"Error adding barcode to product: {e}")
        return False
    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()


def update_barcode_produk(barcode_id, nama_barang, kategori_id, harga_beli, harga_jual, stok, jumlah_label, deskripsi, user_id=None):
    """Update barcode product."""
    try:
        connection = get_db_connection()
        if connection:
            cursor = connection.cursor(dictionary=True)
            if user_id is not None:
                cursor.execute("SELECT ean13 FROM barcode_produk WHERE id = %s AND user_id = %s", (barcode_id, user_id))
            else:
                cursor.execute("SELECT ean13 FROM barcode_produk WHERE id = %s", (barcode_id,))
            existing = cursor.fetchone()
            if existing is None:
                cursor.close()
                connection.close()
                return False
            ean13 = existing['ean13']

            if user_id is not None:
                cursor.execute("""
                    UPDATE barcode_produk
                    SET nama_barang=%s, kategori_id=%s, harga_beli=%s, harga_jual=%s, stok=%s, jumlah_label=%s, deskripsi=%s
                    WHERE id=%s AND user_id=%s
                """, (nama_barang, kategori_id, harga_beli, harga_jual, stok, jumlah_label, deskripsi, barcode_id, user_id))
            else:
                cursor.execute("""
                    UPDATE barcode_produk
                    SET nama_barang=%s, kategori_id=%s, harga_beli=%s, harga_jual=%s, stok=%s, jumlah_label=%s, deskripsi=%s
                    WHERE id=%s
                """, (nama_barang, kategori_id, harga_beli, harga_jual, stok, jumlah_label, deskripsi, barcode_id))

            if cursor.rowcount == 0:
                cursor.close()
                connection.close()
                return False

            connection.commit()
            sync_barcode_to_barang(ean13, nama_barang, kategori_id, harga_beli, harga_jual, stok, deskripsi, user_id=user_id)
            cursor.close()
            connection.close()
            return True
    except Error as e:
        print(f"Error updating barcode product: {e}")
        return False

    return False


def delete_barcode_produk(barcode_id, user_id=None):
    """Remove a barcode record and detach it from its existing product."""
    connection = None
    cursor = None
    try:
        connection = get_db_connection()
        if not connection:
            return False

        cursor = connection.cursor(dictionary=True)
        if user_id is not None:
            cursor.execute("SELECT * FROM barcode_produk WHERE id = %s AND user_id = %s", (barcode_id, user_id))
        else:
            cursor.execute("SELECT * FROM barcode_produk WHERE id = %s", (barcode_id,))
        barcode = cursor.fetchone()
        if not barcode:
            return False

        if barcode.get('barang_id') is not None:
            cursor.execute("UPDATE barang SET barcode = NULL WHERE id = %s AND barcode = %s", (barcode['barang_id'], barcode['ean13']))
        elif user_id is not None:
            cursor.execute("UPDATE barang SET barcode = NULL WHERE barcode = %s AND user_id = %s", (barcode['ean13'], user_id))
        else:
            cursor.execute("UPDATE barang SET barcode = NULL WHERE barcode = %s", (barcode['ean13'],))

        if user_id is not None:
            cursor.execute("DELETE FROM barcode_produk WHERE id = %s AND user_id = %s", (barcode_id, user_id))
        else:
            cursor.execute("DELETE FROM barcode_produk WHERE id = %s", (barcode_id,))
        deleted = cursor.rowcount > 0
        connection.commit()
        return deleted
    except Error as e:
        if connection:
            connection.rollback()
        print(f"Error deleting barcode product: {e}")
        return False
    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()


def add_kategori(nama_kategori, deskripsi, user_id=None):
    """Add new kategori"""
    try:
        connection = get_db_connection()
        if connection:
            cursor = connection.cursor()
            cursor.execute("""
                INSERT INTO kategori (nama_kategori, deskripsi, user_id)
                VALUES (%s, %s, %s)
            """, (nama_kategori, deskripsi, user_id))
            connection.commit()
            cursor.close()
            connection.close()
            return True
    except Error as e:
        print(f"Error adding kategori: {e}")
        return False
    
    return False

def update_kategori(kategori_id, nama_kategori, deskripsi, user_id=None):
    """Update kategori"""
    try:
        connection = get_db_connection()
        if connection:
            cursor = connection.cursor()
            if user_id is not None:
                cursor.execute("""
                    UPDATE kategori 
                    SET nama_kategori=%s, deskripsi=%s
                    WHERE id=%s AND user_id=%s
                """, (nama_kategori, deskripsi, kategori_id, user_id))
            else:
                cursor.execute("""
                    UPDATE kategori 
                    SET nama_kategori=%s, deskripsi=%s
                    WHERE id=%s
                """, (nama_kategori, deskripsi, kategori_id))
            connection.commit()
            cursor.close()
            connection.close()
            return True
    except Error as e:
        print(f"Error updating kategori: {e}")
        return False
    
    return False

def delete_kategori(kategori_id, user_id=None):
    """Delete kategori"""
    try:
        connection = get_db_connection()
        if connection:
            cursor = connection.cursor()
            if user_id is not None:
                cursor.execute("DELETE FROM kategori WHERE id = %s AND user_id = %s", (kategori_id, user_id))
            else:
                cursor.execute("DELETE FROM kategori WHERE id = %s", (kategori_id,))
            connection.commit()
            cursor.close()
            connection.close()
            return True
    except Error as e:
        print(f"Error deleting kategori: {e}")
        return False
    
    return False

def get_all_users(owner_id=None):
    """Get all users for a specific owner admin."""
    connection = get_db_connection()
    user_list = []
    
    if connection:
        cursor = connection.cursor(dictionary=True)
        if owner_id is not None:
            cursor.execute("SELECT id, username, nama_lengkap, role FROM users WHERE owner_id = %s OR id = %s ORDER BY nama_lengkap", (owner_id, owner_id))
        else:
            cursor.execute("SELECT id, username, nama_lengkap, role FROM users ORDER BY nama_lengkap")
        user_list = cursor.fetchall()
        cursor.close()
        connection.close()
    
    return user_list

def get_user_by_id(user_id):
    """Get user by id"""
    connection = get_db_connection()
    user = None
    if connection:
        cursor = connection.cursor(dictionary=True)
        cursor.execute("SELECT id, username, nama_lengkap, role, profile_photo FROM users WHERE id = %s", (user_id,))
        user = cursor.fetchone()
        cursor.close()
        connection.close()
    return user


def add_user(username, password, nama_lengkap, role, owner_id=None):
    """Add new user"""
    try:
        connection = get_db_connection()
        if connection:
            cursor = connection.cursor()
            cursor.execute("""
                INSERT INTO users (username, password, nama_lengkap, role, owner_id)
                VALUES (%s, %s, %s, %s, %s)
            """, (username, password, nama_lengkap, role, owner_id))
            connection.commit()
            cursor.close()
            connection.close()
            return True
    except Error as e:
        print(f"Error adding user: {e}")
        return False
    
    return False

def update_user(user_id, username, password, nama_lengkap, role, owner_id=None):
    """Update user"""
    try:
        connection = get_db_connection()
        if connection:
            cursor = connection.cursor()
            if password:
                if owner_id is not None:
                    cursor.execute("""
                        UPDATE users 
                        SET username=%s, password=%s, nama_lengkap=%s, role=%s
                        WHERE id=%s AND (owner_id = %s OR id = %s)
                    """, (username, password, nama_lengkap, role, user_id, owner_id, owner_id))
                else:
                    cursor.execute("""
                        UPDATE users 
                        SET username=%s, password=%s, nama_lengkap=%s, role=%s
                        WHERE id=%s
                    """, (username, password, nama_lengkap, role, user_id))
            else:
                if owner_id is not None:
                    cursor.execute("""
                        UPDATE users 
                        SET username=%s, nama_lengkap=%s, role=%s
                        WHERE id=%s AND (owner_id = %s OR id = %s)
                    """, (username, nama_lengkap, role, user_id, owner_id, owner_id))
                else:
                    cursor.execute("""
                        UPDATE users 
                        SET username=%s, nama_lengkap=%s, role=%s
                        WHERE id=%s
                    """, (username, nama_lengkap, role, user_id))
            connection.commit()
            cursor.close()
            connection.close()
            return True
    except Error as e:
        print(f"Error updating user: {e}")
        return False
    
    return False

def delete_user(user_id, owner_id=None):
    """Delete user"""
    try:
        connection = get_db_connection()
        if connection:
            cursor = connection.cursor()
            if owner_id is not None:
                cursor.execute("DELETE FROM users WHERE id = %s AND (owner_id = %s OR id = %s)", (user_id, owner_id, owner_id))
            else:
                cursor.execute("DELETE FROM users WHERE id = %s", (user_id,))
            connection.commit()
            cursor.close()
            connection.close()
            return True
    except Error as e:
        print(f"Error deleting user: {e}")
        return False
    
    return False

def get_account_owner_id(user_id):
    """Resolve an admin or cashier to the account that owns shared data."""
    connection = get_db_connection()
    if not connection:
        return user_id

    cursor = connection.cursor(dictionary=True)
    cursor.execute("SELECT role, owner_id FROM users WHERE id = %s", (user_id,))
    user = cursor.fetchone()
    cursor.close()
    connection.close()
    if not user:
        return user_id
    return user_id if user['role'] == 'admin' else (user.get('owner_id') or user_id)


def get_store_settings(owner_id):
    """Get settings for a store owner, returning defaults when none are saved yet."""
    settings = {
        'owner_id': owner_id,
        'nama_toko': 'Kasir POS',
        'alamat': '',
        'telepon': '',
        'email': '',
        'notification_email': '',
        'logo': None,
        'footer_message': 'Terima kasih atas kunjungan Anda',
        'low_stock_threshold': 10,
        'email_notification': 0,
    }
    connection = get_db_connection()
    if not connection:
        return settings

    cursor = connection.cursor(dictionary=True)
    cursor.execute("SELECT * FROM settings WHERE owner_id = %s LIMIT 1", (owner_id,))
    result = cursor.fetchone()
    cursor.close()
    connection.close()
    if result:
        settings.update(result)
        if settings['low_stock_threshold'] is None:
            settings['low_stock_threshold'] = 10
        if settings['email_notification'] is None:
            settings['email_notification'] = 0
        if settings['notification_email'] is None:
            settings['notification_email'] = ''
    return settings


def _account_transaction_scope(user_id, alias='t'):
    if user_id is None:
        return '', ()
    return (
        f" AND {alias}.user_id IN (SELECT id FROM users WHERE id = %s OR owner_id = %s)",
        (user_id, user_id)
    )


def get_all_members(owner_id):
    connection = get_db_connection()
    members = []
    if connection:
        cursor = connection.cursor(dictionary=True)
        cursor.execute("SELECT * FROM member WHERE owner_id = %s ORDER BY nama", (owner_id,))
        members = cursor.fetchall()
        cursor.close()
        connection.close()
    return members


def get_member_by_id(member_id, owner_id, active_only=False):
    connection = get_db_connection()
    if not connection:
        return None
    cursor = connection.cursor(dictionary=True)
    query = "SELECT * FROM member WHERE id = %s AND owner_id = %s"
    if active_only:
        query += " AND aktif = 1"
    cursor.execute(query, (member_id, owner_id))
    member = cursor.fetchone()
    cursor.close()
    connection.close()
    return member


def get_member_by_name(nama, owner_id):
    connection = get_db_connection()
    if not connection:
        return None
    cursor = connection.cursor(dictionary=True)
    cursor.execute("""
        SELECT id, nama, diskon_persen
        FROM member
        WHERE owner_id = %s AND aktif = 1 AND LOWER(TRIM(nama)) = LOWER(TRIM(%s))
        LIMIT 1
    """, (owner_id, nama))
    member = cursor.fetchone()
    cursor.close()
    connection.close()
    return member


def add_member(owner_id, nama, telepon, email, alamat, diskon_persen):
    try:
        connection = get_db_connection()
        if connection:
            cursor = connection.cursor()
            cursor.execute("""
                INSERT INTO member (owner_id, nama, telepon, email, alamat, diskon_persen)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (owner_id, nama, telepon, email or None, alamat or None, diskon_persen))
            connection.commit()
            cursor.close()
            connection.close()
            return True
    except Error as e:
        print(f"Error adding member: {e}")
    return False


def update_member(member_id, owner_id, nama, telepon, email, alamat, diskon_persen, aktif):
    try:
        connection = get_db_connection()
        if connection:
            cursor = connection.cursor()
            cursor.execute("""
                UPDATE member
                SET nama=%s, telepon=%s, email=%s, alamat=%s, diskon_persen=%s, aktif=%s
                WHERE id=%s AND owner_id=%s
            """, (nama, telepon, email or None, alamat or None, diskon_persen, aktif, member_id, owner_id))
            connection.commit()
            cursor.close()
            connection.close()
            return True
    except Error as e:
        print(f"Error updating member: {e}")
    return False


def delete_member(member_id, owner_id):
    try:
        connection = get_db_connection()
        if connection:
            cursor = connection.cursor()
            cursor.execute("DELETE FROM member WHERE id = %s AND owner_id = %s", (member_id, owner_id))
            connection.commit()
            deleted = cursor.rowcount > 0
            cursor.close()
            connection.close()
            return deleted
    except Error as e:
        print(f"Error deleting member: {e}")
    return False


def save_transaksi(kode_transaksi, user_id, total, metode_pembayaran, jumlah_bayar, kembalian, cart, nama_pelanggan=None, member_id=None, diskon_persen=0, diskon_nominal=0):
    """Save transaction"""
    connection = None
    cursor = None
    try:
        connection = get_db_connection()
        if not connection:
            return False

        cursor = connection.cursor()

        cursor.execute("""
            INSERT INTO transaksi (kode_transaksi, user_id, total, metode_pembayaran, jumlah_bayar, kembalian, nama_pelanggan, member_id, diskon_persen, diskon_nominal)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (kode_transaksi, user_id, total, metode_pembayaran, jumlah_bayar, kembalian, nama_pelanggan, member_id, diskon_persen, diskon_nominal))

        transaksi_id = cursor.lastrowid

        for item in cart:
            cursor.execute("SELECT harga_beli FROM barang WHERE id = %s", (item['id'],))
            barang_cost = cursor.fetchone()
            harga_modal = barang_cost[0] if barang_cost else None
            cursor.execute("""
                INSERT INTO detail_transaksi (transaksi_id, barang_id, harga_saat_transaksi, harga_modal_saat_transaksi, jumlah, subtotal)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (transaksi_id, item['id'], item['harga_jual'], harga_modal, item['jumlah'], item['subtotal']))

        connection.commit()
        return True
    except Error as e:
        if connection:
            connection.rollback()
        print(f"Error saving transaction: {e}")
        return False
    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()

def get_transactions(limit=50, user_id=None):
    """Get transactions"""
    connection = get_db_connection()
    transactions = []
    
    if connection:
        cursor = connection.cursor(dictionary=True)
        if user_id is not None:
            scope, params = _account_transaction_scope(user_id)
            cursor.execute("""
                SELECT t.*, u.nama_lengkap as nama_kasir
                FROM transaksi t
                JOIN users u ON t.user_id = u.id
                WHERE 1=1
            """ + scope + """
                ORDER BY t.created_at DESC
                LIMIT %s
            """, (*params, limit))
        else:
            cursor.execute("""
                SELECT t.*, u.nama_lengkap as nama_kasir
                FROM transaksi t
                JOIN users u ON t.user_id = u.id
                ORDER BY t.created_at DESC
                LIMIT %s
            """, (limit,))
        transactions = cursor.fetchall()
        cursor.close()
        connection.close()
    
    return transactions

def get_transaction_detail(kode_transaksi, user_id=None):
    """Get transaction detail by kode"""
    connection = get_db_connection()
    transaction = None
    
    if connection:
        cursor = connection.cursor(dictionary=True)
        if user_id is not None:
            scope, params = _account_transaction_scope(user_id)
            cursor.execute("""
                SELECT t.*, u.nama_lengkap as nama_kasir
                FROM transaksi t
                JOIN users u ON t.user_id = u.id
                WHERE t.kode_transaksi = %s
            """ + scope, (kode_transaksi, *params))
        else:
            cursor.execute("""
                SELECT t.*, u.nama_lengkap as nama_kasir
                FROM transaksi t
                JOIN users u ON t.user_id = u.id
                WHERE t.kode_transaksi = %s
            """, (kode_transaksi,))
        transaction = cursor.fetchone()
        
        if transaction:
            # Get transaction details
            cursor.execute("""
                SELECT dt.*, b.nama_barang, b.kode_barang
                FROM detail_transaksi dt
                JOIN barang b ON dt.barang_id = b.id
                WHERE dt.transaksi_id = %s
            """, (transaction['id'],))
            details = cursor.fetchall()
            
            # Format details
            detail_list = []
            for d in details:
                detail_list.append({
                    'nama_barang': d['nama_barang'],
                    'kode_barang': d['kode_barang'],
                    'jumlah': d['jumlah'],
                    'harga': d['harga_saat_transaksi'],
                    'subtotal': d['subtotal']
                })
            
            transaction['detail'] = detail_list
            transaction['tanggal'] = transaction['created_at'].strftime('%d-%m-%Y %H:%M')
        
        cursor.close()
        connection.close()
    
    return transaction

def get_dashboard_data(user_id=None, inventory_user_id=None, low_stock_threshold=10):
    """Get dashboard data"""
    connection = get_db_connection()
    data = {}
    if inventory_user_id is None:
        inventory_user_id = user_id
    
    if connection:
        cursor = connection.cursor(dictionary=True)
        today = datetime.now().strftime('%Y-%m-%d')
        transaction_scope, scope_params = _account_transaction_scope(user_id)
        
        # Today's transactions count
        cursor.execute("""
            SELECT COUNT(*) as count FROM transaksi t
            WHERE DATE(t.created_at) = %s AND t.status = 'selesai'
        """ + transaction_scope, (today, *scope_params))
        result = cursor.fetchone()
        data['transaksi_hari_ini'] = result['count'] if result else 0
        
        # Today's revenue
        cursor.execute("""
            SELECT SUM(t.total) as total FROM transaksi t
            WHERE DATE(t.created_at) = %s AND t.status = 'selesai'
        """ + transaction_scope, (today, *scope_params))
        result = cursor.fetchone()
        data['pendapatan_harian'] = float(result['total']) if result and result['total'] else 0
        
        # Today's items sold
        cursor.execute("""
            SELECT SUM(dt.jumlah) as total FROM detail_transaksi dt
            JOIN transaksi t ON dt.transaksi_id = t.id
            WHERE DATE(t.created_at) = %s AND t.status = 'selesai'
        """ + transaction_scope, (today, *scope_params))
        result = cursor.fetchone()
        data['items_hari_ini'] = int(result['total']) if result and result['total'] else 0
        
        # Total barang
        if inventory_user_id is not None:
            cursor.execute("SELECT COUNT(*) as count FROM barang WHERE user_id = %s", (inventory_user_id,))
        else:
            cursor.execute("SELECT COUNT(*) as count FROM barang")
        result = cursor.fetchone()
        data['total_barang'] = result['count'] if result else 0
        
        # Total kategori
        if inventory_user_id is not None:
            cursor.execute("SELECT COUNT(*) as count FROM kategori WHERE user_id = %s OR user_id IS NULL", (inventory_user_id,))
        else:
            cursor.execute("SELECT COUNT(*) as count FROM kategori")
        result = cursor.fetchone()
        data['total_kategori'] = result['count'] if result else 0
        
        # Low stock items
        if inventory_user_id is not None:
            cursor.execute(
                "SELECT COUNT(*) as count FROM barang WHERE stok <= %s AND user_id = %s",
                (low_stock_threshold, inventory_user_id)
            )
        else:
            cursor.execute("SELECT COUNT(*) as count FROM barang WHERE stok <= %s", (low_stock_threshold,))
        result = cursor.fetchone()
        data['low_stock'] = result['count'] if result else 0
        
        # Recent transactions
        cursor.execute("""
            SELECT t.kode_transaksi, t.created_at, t.total, t.metode_pembayaran
            FROM transaksi t
            WHERE 1=1
        """ + transaction_scope + """
            ORDER BY t.created_at DESC
            LIMIT 5
        """, scope_params)
        data['transaksi_terakhir'] = cursor.fetchall()
        
        cursor.close()
        connection.close()
    
    return data

def get_laporan_data(jenis_laporan, tanggal, user_id=None):
    """Get laporan data"""
    connection = get_db_connection()
    data = {'total_keuntungan': 0, 'total_modal': 0}
    
    if connection:
        cursor = connection.cursor(dictionary=True)
        transaction_scope, scope_params = _account_transaction_scope(user_id)
        
        if jenis_laporan == 'harian':
            # Daily report
            cursor.execute("""
                SELECT t.*, u.nama_lengkap as nama_kasir
                FROM transaksi t
                JOIN users u ON t.user_id = u.id
                WHERE DATE(t.created_at) = %s AND t.status = 'selesai'
            """ + transaction_scope + """
                ORDER BY t.created_at DESC
            """, (tanggal, *scope_params))
            transactions = cursor.fetchall()
            
            cursor.execute("""
                SELECT COUNT(*) as count, SUM(t.total) as total
                FROM transaksi t
                WHERE DATE(t.created_at) = %s AND t.status = 'selesai'
            """ + transaction_scope, (tanggal, *scope_params))
            result = cursor.fetchone()
            
            data['total_transaksi'] = result['count'] if result and result['count'] else 0
            data['total_pendapatan'] = float(result['total']) if result and result['total'] else 0
            data['transaksi'] = transactions
            
        elif jenis_laporan == 'mingguan':
            # Weekly report
            start_date = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
            cursor.execute("""
                SELECT t.*, u.nama_lengkap as nama_kasir
                FROM transaksi t
                JOIN users u ON t.user_id = u.id
                WHERE DATE(t.created_at) BETWEEN %s AND %s AND t.status = 'selesai'
            """ + transaction_scope + """
                ORDER BY t.created_at DESC
            """, (start_date, tanggal, *scope_params))
            transactions = cursor.fetchall()
            
            cursor.execute("""
                SELECT COUNT(*) as count, SUM(t.total) as total
                FROM transaksi t
                WHERE DATE(t.created_at) BETWEEN %s AND %s AND t.status = 'selesai'
            """ + transaction_scope, (start_date, tanggal, *scope_params))
            result = cursor.fetchone()
            
            data['total_transaksi'] = result['count'] if result and result['count'] else 0
            data['total_pendapatan'] = float(result['total']) if result and result['total'] else 0
            data['transaksi'] = transactions
            
        elif jenis_laporan == 'bulanan':
            # Monthly report
            bulan = tanggal[:7] + '%'
            cursor.execute("""
                SELECT t.*, u.nama_lengkap as nama_kasir
                FROM transaksi t
                JOIN users u ON t.user_id = u.id
                WHERE DATE(t.created_at) LIKE %s AND t.status = 'selesai'
            """ + transaction_scope + """
                ORDER BY t.created_at DESC
            """, (bulan, *scope_params))
            transactions = cursor.fetchall()
            
            cursor.execute("""
                SELECT COUNT(*) as count, SUM(t.total) as total
                FROM transaksi t
                WHERE DATE(t.created_at) LIKE %s AND t.status = 'selesai'
            """ + transaction_scope, (bulan, *scope_params))
            result = cursor.fetchone()
            
            data['total_transaksi'] = result['count'] if result and result['count'] else 0
            data['total_pendapatan'] = float(result['total']) if result and result['total'] else 0
            data['transaksi'] = transactions

        transaction_ids = [transaction['id'] for transaction in data.get('transaksi', [])]
        if transaction_ids:
            placeholders = ','.join(['%s'] * len(transaction_ids))
            cursor.execute(
                f"""
                SELECT dt.transaksi_id,
                       SUM(dt.jumlah * COALESCE(dt.harga_modal_saat_transaksi, b.harga_beli)) AS total_modal
                FROM detail_transaksi dt
                JOIN barang b ON b.id = dt.barang_id
                WHERE dt.transaksi_id IN ({placeholders})
                GROUP BY dt.transaksi_id
                """,
                transaction_ids
            )
            modal_by_transaction = {
                row['transaksi_id']: float(row['total_modal'] or 0)
                for row in cursor.fetchall()
            }
            data['total_modal'] = sum(modal_by_transaction.values())
            for transaction in data.get('transaksi', []):
                margin = float(transaction.get('total') or 0) - modal_by_transaction.get(transaction['id'], 0)
                if margin >= 0:
                    data['total_keuntungan'] += margin

            cursor.execute(
                f"SELECT COALESCE(SUM(jumlah), 0) AS total FROM detail_transaksi WHERE transaksi_id IN ({placeholders})",
                transaction_ids
            )
            item_result = cursor.fetchone()
            data['total_items'] = int(item_result['total'] or 0)
        else:
            data['total_items'] = 0
        
        # Average transaction
        if data.get('total_transaksi', 0) > 0:
            data['rata_rata'] = data['total_pendapatan'] / data['total_transaksi']
        else:
            data['rata_rata'] = 0
        
        cursor.close()
        connection.close()
    
    return data

def export_to_pdf(jenis_laporan, tanggal, user_id=None):
    """Export a formatted POS sales report to PDF."""
    from io import BytesIO
    from flask import make_response
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from xml.sax.saxutils import escape
    
    data = get_laporan_data(jenis_laporan, tanggal, user_id=user_id)
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=15 * mm,
        leftMargin=15 * mm,
        topMargin=15 * mm,
        bottomMargin=18 * mm
    )
    elements = []
    styles = getSampleStyleSheet()

    ink = colors.HexColor('#233b53')
    accent = colors.HexColor('#4f46e5')
    muted = colors.HexColor('#64748b')
    border = colors.HexColor('#cbd5e1')
    pale = colors.HexColor('#f1f5f9')
    page_width = doc.width
    cell_style = ParagraphStyle(
        'ReportTableCell',
        parent=styles['BodyText'],
        fontName='Helvetica',
        fontSize=7.2,
        leading=9,
        textColor=ink,
        wordWrap='CJK'
    )
    header_cell_style = ParagraphStyle(
        'ReportTableHeader',
        parent=cell_style,
        fontName='Helvetica-Bold',
        fontSize=7,
        leading=8,
        textColor=colors.white,
        alignment=1
    )
    section_style = ParagraphStyle(
        'ReportSectionTitle',
        parent=styles['BodyText'],
        fontName='Helvetica-Bold',
        fontSize=8,
        leading=10,
        textColor=colors.white
    )
    brand_style = ParagraphStyle(
        'ReportBrand',
        parent=styles['BodyText'],
        fontName='Helvetica-Bold',
        fontSize=13,
        leading=16,
        textColor=ink
    )
    title_style = ParagraphStyle(
        'ReportTitle',
        parent=styles['BodyText'],
        fontName='Helvetica-Bold',
        fontSize=13,
        leading=16,
        textColor=accent,
        alignment=2
    )
    meta_style = ParagraphStyle(
        'ReportMeta',
        parent=styles['BodyText'],
        fontSize=8,
        leading=11,
        textColor=ink
    )
    summary_style = ParagraphStyle(
        'ReportSummary',
        parent=styles['BodyText'],
        fontSize=7,
        leading=9,
        textColor=muted
    )

    header = Table(
        [[
            Paragraph('KASIR POS<br/><font size="7">LAPORAN OPERASIONAL</font>', brand_style),
            Paragraph('LAPORAN PENJUALAN', title_style)
        ]],
        colWidths=[page_width * 0.48, page_width * 0.52]
    )
    header.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LINEBELOW', (0, 0), (-1, -1), 1.4, accent),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 9),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0)
    ]))
    elements.append(header)
    elements.append(Spacer(1, 7 * mm))

    try:
        report_date = datetime.strptime(str(tanggal), '%Y-%m-%d').strftime('%d-%m-%Y')
    except ValueError:
        report_date = str(tanggal)
    generated_at = datetime.now().strftime('%d-%m-%Y %H:%M')
    meta = Table(
        [[
            Paragraph(f'<b>Jenis laporan:</b> {escape(str(jenis_laporan).capitalize())}', meta_style),
            Paragraph(f'<b>Tanggal acuan:</b> {escape(report_date)}', meta_style),
            Paragraph(f'<b>Dicetak:</b> {escape(generated_at)}', meta_style)
        ]],
        colWidths=[page_width * 0.34, page_width * 0.32, page_width * 0.34]
    )
    meta.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), pale),
        ('BOX', (0, 0), (-1, -1), 0.6, border),
        ('INNERGRID', (0, 0), (-1, -1), 0.4, border),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 7),
        ('RIGHTPADDING', (0, 0), (-1, -1), 7),
        ('TOPPADDING', (0, 0), (-1, -1), 7),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 7)
    ]))
    elements.append(meta)
    elements.append(Spacer(1, 6 * mm))

    def section_bar(title):
        bar = Table([[Paragraph(title, section_style)]], colWidths=[page_width])
        bar.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), ink),
            ('LEFTPADDING', (0, 0), (-1, -1), 8),
            ('RIGHTPADDING', (0, 0), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6)
        ]))
        return bar

    def format_currency(value):
        return 'Rp ' + format(int(round(float(value or 0))), ',d').replace(',', '.')

    elements.append(section_bar('RINGKASAN PENJUALAN'))
    summary_values = [
        ('Total transaksi', str(data.get('total_transaksi', 0))),
        ('Pendapatan', format_currency(data.get('total_pendapatan', 0))),
        ('Item terjual', str(data.get('total_items', 0))),
        ('Keuntungan', format_currency(data.get('total_keuntungan', 0))),
        ('Modal', format_currency(data.get('total_modal', 0)))
    ]
    summary_cells = [
        Paragraph(f'{escape(label)}<br/><b><font size="10" color="#233b53">{escape(value)}</font></b>', summary_style)
        for label, value in summary_values
    ]
    summary_data = [
        summary_cells[:3],
        summary_cells[3:] + [Paragraph('', summary_style)]
    ]
    summary_table = Table(summary_data, colWidths=[page_width / 3] * 3)
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.white),
        ('ROWBACKGROUNDS', (0, 0), (-1, -1), [colors.white, pale]),
        ('BOX', (0, 0), (-1, -1), 0.6, border),
        ('INNERGRID', (0, 0), (-1, -1), 0.4, border),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 7),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 7)
    ]))
    elements.append(summary_table)
    elements.append(Spacer(1, 6 * mm))
    elements.append(section_bar('DAFTAR TRANSAKSI'))
    elements.append(Spacer(1, 2 * mm))

    table_data = [[
        Paragraph('KODE<br/>TRANSAKSI', header_cell_style),
        Paragraph('TANGGAL', header_cell_style),
        Paragraph('PELANGGAN', header_cell_style),
        Paragraph('KASIR', header_cell_style),
        Paragraph('TOTAL', header_cell_style),
        Paragraph('PEMBAYARAN', header_cell_style),
        Paragraph('STATUS', header_cell_style)
    ]]

    transactions = data.get('transaksi', [])
    for trx in transactions:
        created_at = trx.get('created_at', '')
        if hasattr(created_at, 'strftime'):
            created_at = created_at.strftime('%d-%m-%Y %H:%M')
        elif created_at:
            try:
                created_at = datetime.fromisoformat(str(created_at)).strftime('%d-%m-%Y %H:%M')
            except ValueError:
                created_at = str(created_at)
        table_data.append([
            Paragraph(escape(str(trx.get('kode_transaksi', ''))), cell_style),
            Paragraph(escape(str(created_at)), cell_style),
            Paragraph(escape(str(trx.get('nama_pelanggan') or 'Umum')), cell_style),
            Paragraph(escape(str(trx.get('nama_kasir', ''))), cell_style),
            Paragraph(escape(format_currency(trx.get('total', 0))), cell_style),
            Paragraph(escape(str(trx.get('metode_pembayaran', ''))), cell_style),
            Paragraph(escape(str(trx.get('status', ''))), cell_style)
        ])
    if not transactions:
        table_data.append([
            '', '', Paragraph('Tidak ada transaksi pada periode ini.', cell_style),
            '', '', '', ''
        ])

    col_widths = [
        page_width * 0.14,
        page_width * 0.15,
        page_width * 0.16,
        page_width * 0.15,
        page_width * 0.16,
        page_width * 0.14,
        page_width * 0.10
    ]
    table = Table(table_data, colWidths=col_widths, repeatRows=1, hAlign='LEFT')
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), ink),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, pale]),
        ('TEXTCOLOR', (0, 1), (-1, -1), ink),
        ('GRID', (0, 0), (-1, -1), 0.45, border),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN', (4, 1), (4, -1), 'RIGHT'),
        ('ALIGN', (6, 1), (6, -1), 'CENTER'),
        ('SPAN', (0, 1), (-1, 1)) if not transactions else ('ALIGN', (0, 1), (0, -1), 'LEFT'),
        ('LEFTPADDING', (0, 0), (-1, -1), 5),
        ('RIGHTPADDING', (0, 0), (-1, -1), 5),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5)
    ]))
    elements.append(table)

    def draw_page_footer(canvas, document):
        canvas.saveState()
        canvas.setStrokeColor(border)
        canvas.setLineWidth(0.5)
        canvas.line(document.leftMargin, 12 * mm, A4[0] - document.rightMargin, 12 * mm)
        canvas.setFont('Helvetica', 7)
        canvas.setFillColor(muted)
        canvas.drawString(document.leftMargin, 8 * mm, 'Kasir POS  |  Laporan penjualan')
        canvas.drawRightString(A4[0] - document.rightMargin, 8 * mm, f'Halaman {document.page}')
        canvas.restoreState()

    doc.build(elements, onFirstPage=draw_page_footer, onLaterPages=draw_page_footer)

    buffer.seek(0)
    response = make_response(buffer.getvalue())
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = 'attachment; filename=laporan_' + jenis_laporan + '_' + tanggal + '.pdf'
    
    return response

def export_to_excel(jenis_laporan, tanggal, user_id=None):
    """Export to Excel"""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.worksheet.table import Table, TableStyleInfo
    from flask import make_response
    from datetime import date, datetime
    
    # Get laporan data
    data = get_laporan_data(jenis_laporan, tanggal, user_id=user_id)
    
    wb = Workbook()
    ws = wb.active
    ws.title = 'Laporan'
    ws.sheet_view.showGridLines = False
    ws.sheet_properties.tabColor = '0F766E'
    
    navy = '17324D'
    teal = '0F766E'
    light_teal = 'E6F4F1'
    light_gray = 'F3F6F8'
    border_color = 'D7E0E7'
    white = 'FFFFFF'
    thin_border = Border(
        left=Side(style='thin', color=border_color),
        right=Side(style='thin', color=border_color),
        top=Side(style='thin', color=border_color),
        bottom=Side(style='thin', color=border_color)
    )
    
    ws.merge_cells('A1:H1')
    ws['A1'] = 'LAPORAN KASIR POS'
    ws['A1'].font = Font(name='Calibri', size=18, bold=True, color=white)
    ws['A1'].fill = PatternFill('solid', fgColor=navy)
    ws['A1'].alignment = Alignment(vertical='center')
    ws.row_dimensions[1].height = 34
    
    period_labels = {'harian': 'Harian', 'mingguan': 'Mingguan', 'bulanan': 'Bulanan'}
    ws.merge_cells('A2:H2')
    ws['A2'] = f"Jenis Laporan: {period_labels.get(jenis_laporan, jenis_laporan.capitalize())}  |  Tanggal Acuan: {tanggal}"
    ws['A2'].font = Font(name='Calibri', size=10, color='526477')
    ws['A2'].alignment = Alignment(vertical='center')
    ws.row_dimensions[2].height = 22
    
    ws.merge_cells('A4:H4')
    ws['A4'] = 'RINGKASAN TRANSAKSI'
    ws['A4'].font = Font(name='Calibri', size=11, bold=True, color=white)
    ws['A4'].fill = PatternFill('solid', fgColor=teal)
    ws['A4'].alignment = Alignment(vertical='center')
    ws.row_dimensions[4].height = 23

    summary_cards = [
        ('A5:B5', 'A6:B6', 'Total Transaksi', int(data.get('total_transaksi', 0) or 0), '#,##0'),
        ('C5:D5', 'C6:D6', 'Total Pendapatan', float(data.get('total_pendapatan', 0) or 0), '"Rp" #,##0'),
        ('E5:F5', 'E6:F6', 'Total Keuntungan', float(data.get('total_keuntungan', 0) or 0), '"Rp" #,##0'),
        ('G5:H5', 'G6:H6', 'Total Modal', float(data.get('total_modal', 0) or 0), '"Rp" #,##0')
    ]
    for label_range, value_range, label, value, number_format in summary_cards:
        ws.merge_cells(label_range)
        ws.merge_cells(value_range)
        label_cell = ws[label_range.split(':')[0]]
        value_cell = ws[value_range.split(':')[0]]
        label_cell.value = label
        label_cell.font = Font(name='Calibri', size=10, bold=True, color='526477')
        label_cell.fill = PatternFill('solid', fgColor=light_gray)
        label_cell.alignment = Alignment(horizontal='center', vertical='center')
        value_cell.value = value
        value_cell.font = Font(name='Calibri', size=14, bold=True, color=teal)
        value_cell.fill = PatternFill('solid', fgColor=light_teal)
        value_cell.alignment = Alignment(horizontal='center', vertical='center')
        value_cell.number_format = number_format
    ws.row_dimensions[5].height = 22
    ws.row_dimensions[6].height = 30

    ws.merge_cells('A7:H7')
    ws['A7'] = 'Jumlah Item Terjual'
    ws['A7'].font = Font(name='Calibri', size=10, bold=True, color='526477')
    ws['A7'].fill = PatternFill('solid', fgColor=light_gray)
    ws['A7'].alignment = Alignment(horizontal='center', vertical='center')
    ws.merge_cells('A8:H8')
    ws['A8'] = int(data.get('total_items', 0) or 0)
    ws['A8'].font = Font(name='Calibri', size=15, bold=True, color=teal)
    ws['A8'].fill = PatternFill('solid', fgColor=light_teal)
    ws['A8'].alignment = Alignment(horizontal='center', vertical='center')
    ws['A8'].number_format = '#,##0'
    ws.row_dimensions[7].height = 21
    ws.row_dimensions[8].height = 27

    ws.merge_cells('A10:H10')
    ws['A10'] = 'DETAIL TRANSAKSI'
    ws['A10'].font = Font(name='Calibri', size=11, bold=True, color=white)
    ws['A10'].fill = PatternFill('solid', fgColor=teal)
    ws['A10'].alignment = Alignment(vertical='center')
    ws.row_dimensions[10].height = 23

    headers = [
        'No.', 'Kode Transaksi', 'Tanggal', 'Nama Pelanggan',
        'Kasir', 'Total Pembayaran', 'Metode Pembayaran', 'Status'
    ]
    header_row = 11
    for column, header in enumerate(headers, start=1):
        cell = ws.cell(row=header_row, column=column, value=header)
        cell.font = Font(name='Calibri', size=10, bold=True, color=white)
        cell.fill = PatternFill('solid', fgColor=navy)
        cell.alignment = Alignment(horizontal='left' if column in (2, 4, 5, 7, 8) else 'center', vertical='center', wrap_text=True)
        cell.border = thin_border
    ws.row_dimensions[header_row].height = 30

    for row, trx in enumerate(data.get('transaksi', []), start=header_row + 1):
        created_at = trx.get('created_at', '')
        if isinstance(created_at, str):
            try:
                created_at = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
            except ValueError:
                pass

        values = [
            row - header_row,
            trx.get('kode_transaksi', ''),
            created_at,
            trx.get('nama_pelanggan') or 'Umum',
            trx.get('nama_kasir', ''),
            float(trx.get('total', 0) or 0),
            trx.get('metode_pembayaran', ''),
            trx.get('status', '')
        ]
        for column, value in enumerate(values, start=1):
            cell = ws.cell(row=row, column=column, value=value)
            cell.font = Font(name='Calibri', size=10, color=navy)
            cell.fill = PatternFill('solid', fgColor=white if row % 2 else light_gray)
            cell.border = thin_border
            cell.alignment = Alignment(
                horizontal='right' if column == 6 else 'center' if column in (1, 3, 8) else 'left',
                vertical='center'
            )
        ws.cell(row=row, column=3).number_format = 'dd mmm yyyy, hh:mm' if isinstance(created_at, datetime) else 'dd mmm yyyy' if isinstance(created_at, date) else 'General'
        ws.cell(row=row, column=6).number_format = '"Rp" #,##0'
        ws.row_dimensions[row].height = 22
        if str(values[7]).lower() == 'selesai':
            status_cell = ws.cell(row=row, column=8)
            status_cell.font = Font(name='Calibri', size=10, bold=True, color='176B52')
            status_cell.fill = PatternFill('solid', fgColor='E6F4EA')

    last_data_row = header_row + len(data.get('transaksi', []))
    if last_data_row > header_row:
        table = Table(displayName='TabelTransaksi', ref=f'A{header_row}:H{last_data_row}')
        table.tableStyleInfo = TableStyleInfo(
            name='TableStyleMedium2',
            showFirstColumn=False,
            showLastColumn=False,
            showRowStripes=True,
            showColumnStripes=False
        )
        ws.add_table(table)
    else:
        ws.auto_filter.ref = f'A{header_row}:H{header_row}'

    for column, width in {'A': 8, 'B': 24, 'C': 23, 'D': 24, 'E': 25, 'F': 22, 'G': 24, 'H': 16}.items():
        ws.column_dimensions[column].width = width
    ws.freeze_panes = 'A12'
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.page_setup.orientation = 'landscape'
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.print_title_rows = '1:11'
    ws.print_area = f'A1:H{max(last_data_row, header_row)}'
    ws.sheet_view.zoomScale = 90
    
    # Output
    from io import BytesIO
    output = BytesIO()
    wb.save(output)
    output.seek(0)
    
    response = make_response(output.getvalue())
    response.headers['Content-Type'] = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    response.headers['Content-Disposition'] = f'attachment; filename=laporan_{jenis_laporan}_{tanggal}.xlsx'
    return response


def export_barcode_produk_to_pdf(barcode_product):
    """Export one barcode product as printable 50 x 30 mm EAN-13 labels."""
    from io import BytesIO
    from flask import make_response
    from reportlab.graphics import renderPDF
    from reportlab.graphics.barcode import createBarcodeDrawing
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.pdfbase.pdfmetrics import stringWidth
    from reportlab.pdfgen import canvas

    output = BytesIO()
    pdf = canvas.Canvas(output, pagesize=A4)
    page_width, page_height = A4

    label_width = 50 * mm
    label_height = 30 * mm
    horizontal_gap = 2 * mm
    vertical_gap = 1 * mm
    columns = 3
    rows = 9
    grid_width = columns * label_width + (columns - 1) * horizontal_gap
    left_margin = (page_width - grid_width) / 2
    top_margin = 10 * mm
    labels_per_page = columns * rows
    label_index = 0

    if not barcode_product:
        pdf.setFont('Helvetica-Bold', 16)
        pdf.drawCentredString(page_width / 2, page_height - 35 * mm, 'Barcode Produk')
        pdf.setFont('Helvetica', 10)
        pdf.drawCentredString(page_width / 2, page_height - 43 * mm, 'Produk barcode tidak ditemukan.')
    else:
        item = barcode_product
        try:
            quantity = max(1, int(item.get('jumlah_label') or 1))
        except (TypeError, ValueError):
            quantity = 1

        for _ in range(quantity):
            if label_index and label_index % labels_per_page == 0:
                pdf.showPage()

            position = label_index % labels_per_page
            column = position % columns
            row = position // columns
            x = left_margin + column * (label_width + horizontal_gap)
            y = page_height - top_margin - label_height - row * (label_height + vertical_gap)

            pdf.setStrokeColor(colors.HexColor('#C9CED8'))
            pdf.setLineWidth(0.45)
            pdf.roundRect(x, y, label_width, label_height, 2 * mm, stroke=1, fill=0)

            product_name = str(item.get('nama_barang') or '')
            name_font_size = 7
            max_name_width = label_width - 6 * mm
            while name_font_size > 5.5 and stringWidth(product_name, 'Helvetica-Bold', name_font_size) > max_name_width:
                name_font_size -= 0.25
            pdf.setFillColor(colors.HexColor('#202938'))
            pdf.setFont('Helvetica-Bold', name_font_size)
            pdf.drawCentredString(x + label_width / 2, y + label_height - 5 * mm, product_name)

            ean13 = str(item.get('ean13') or '')
            barcode_type = 'EAN13' if len(ean13) == 13 and ean13.isdigit() else 'Code128'
            drawing = createBarcodeDrawing(
                barcode_type,
                value=ean13,
                barHeight=10 * mm,
                humanReadable=False
            )
            barcode_x = x + (label_width - drawing.width) / 2
            renderPDF.draw(drawing, pdf, barcode_x, y + 7 * mm)

            pdf.setFillColor(colors.HexColor('#30394A'))
            pdf.setFont('Helvetica', 7)
            pdf.drawCentredString(x + label_width / 2, y + 4.2 * mm, ean13)

            harga_jual = float(item.get('harga_jual') or 0)
            pdf.setFont('Helvetica-Bold', 7)
            pdf.drawCentredString(x + label_width / 2, y + 1.4 * mm, f"Rp {harga_jual:,.0f}")
            label_index += 1

    pdf.save()
    output.seek(0)
    response = make_response(output.getvalue())
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = f"attachment; filename=barcode_produk_{barcode_product.get('id', 'label')}.pdf"
    return response
