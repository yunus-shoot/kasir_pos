from decimal import Decimal, InvalidOperation

from mysql.connector import Error

from app import get_db_connection


CHART_OF_ACCOUNTS = [
    ('11001', 'Kas', 'aset', 'debit'),
    ('11002', 'Bank', 'aset', 'debit'),
    ('11003', 'Piutang Usaha', 'aset', 'debit'),
    ('11008', 'Persediaan Barang Dagangan', 'aset', 'debit'),
    ('11009', 'Perlengkapan Toko', 'aset', 'debit'),
    ('12001', 'Tanah', 'aset', 'debit'),
    ('12002', 'Bangunan', 'aset', 'debit'),
    ('12003', 'Kendaraan', 'aset', 'debit'),
    ('12004', 'Peralatan Toko', 'aset', 'debit'),
    ('13001', 'Akumulasi Penyusutan Bangunan', 'aset', 'kredit'),
    ('13002', 'Akumulasi Penyusutan Kendaraan', 'aset', 'kredit'),
    ('13003', 'Akumulasi Penyusutan Peralatan Toko', 'aset', 'kredit'),
    ('13100', 'Cadangan Kerugian Piutang', 'aset', 'kredit'),
    ('21001', 'Utang Dagang', 'kewajiban', 'kredit'),
    ('21005', 'Utang Beban', 'kewajiban', 'kredit'),
    ('22001', 'Utang Bank', 'kewajiban', 'kredit'),
    ('22002', 'Utang Bunga', 'kewajiban', 'kredit'),
    ('31001', 'Modal Sendiri', 'ekuitas', 'kredit'),
    ('31002', 'Penyertaan Modal', 'ekuitas', 'kredit'),
    ('31003', 'Laba Ditahan', 'ekuitas', 'kredit'),
    ('31004', 'Laba Periode Berjalan', 'ekuitas', 'kredit'),
    ('32001', 'Prive', 'ekuitas', 'debit'),
    ('41001', 'Penjualan', 'pendapatan', 'kredit'),
    ('41002', 'Pendapatan Lain-Lain', 'pendapatan', 'kredit'),
    ('42001', 'Retur Penjualan', 'pendapatan', 'debit'),
    ('42002', 'Potongan Penjualan', 'pendapatan', 'debit'),
    ('51001', 'Pembelian Barang Dagangan', 'beban', 'debit'),
    ('51002', 'Angkut Pembelian', 'beban', 'debit'),
    ('51003', 'Beban Iklan', 'beban', 'debit'),
    ('51004', 'Beban Pelatihan', 'beban', 'debit'),
    ('51005', 'Beban Bunga', 'beban', 'debit'),
    ('51006', 'Beban Listrik, Air dan Telepon', 'beban', 'debit'),
    ('51007', 'Beban Penyusutan Bangunan', 'beban', 'debit'),
    ('51008', 'Beban Penyusutan Kendaraan', 'beban', 'debit'),
    ('51009', 'Beban Penyusutan Peralatan Toko', 'beban', 'debit'),
    ('51010', 'Beban Perlengkapan Toko', 'beban', 'debit'),
    ('51011', 'Beban Gaji dan Administrasi', 'beban', 'debit'),
    ('51012', 'Beban Perbaikan Kendaraan', 'beban', 'debit'),
    ('51015', 'Harga Pokok Penjualan', 'beban', 'debit'),
    ('51101', 'Harga Pokok Produksi', 'beban', 'debit'),
    ('55001', 'Retur Pembelian', 'beban', 'kredit'),
    ('55002', 'Potongan Pembelian', 'beban', 'kredit'),
]

ZERO = Decimal('0.00')


def validate_journal_lines(lines):
    normalized = []
    debit_total = ZERO
    credit_total = ZERO
    for line in lines:
        try:
            debit = Decimal(str(line['debit'] or 0)).quantize(Decimal('0.01'))
            credit = Decimal(str(line['credit'] or 0)).quantize(Decimal('0.01'))
        except InvalidOperation as error:
            raise ValueError('Nilai debit dan kredit harus berupa angka yang valid.') from error
        if not debit.is_finite() or not credit.is_finite():
            raise ValueError('Nilai debit dan kredit harus berupa angka yang valid.')
        if debit < 0 or credit < 0:
            raise ValueError('Nominal debit dan kredit tidak boleh negatif.')
        if debit > 0 and credit > 0:
            raise ValueError(
                'Satu baris akun hanya boleh diisi di kolom Debit atau Kredit. '
                'Kosongkan salah satunya, lalu masukkan pasangan akun di baris lain.'
            )
        if debit == 0 and credit == 0:
            continue
        normalized.append({
            'account_id': int(line['account_id']),
            'debit': debit,
            'credit': credit,
        })
        debit_total += debit
        credit_total += credit

    if len(normalized) < 2:
        raise ValueError('Jurnal harus memiliki minimal dua baris bernilai.')
    if debit_total != credit_total:
        raise ValueError('Total debit dan kredit harus sama.')
    return normalized


def seed_chart_accounts(owner_id, cursor):
    cursor.executemany("""
        INSERT IGNORE INTO umkm_accounts
            (owner_id, account_code, account_name, account_type, normal_balance)
        VALUES (%s, %s, %s, %s, %s)
    """, [(owner_id, *account) for account in CHART_OF_ACCOUNTS])


def get_accounts(owner_id):
    connection = get_db_connection()
    if not connection:
        raise RuntimeError('Database pembukuan tidak dapat diakses.')
    try:
        cursor = connection.cursor(dictionary=True)
        cursor.execute("""
            SELECT id, account_code, account_name, account_type, normal_balance
            FROM umkm_accounts
            WHERE owner_id = %s AND is_active = 1
            ORDER BY account_code
        """, (owner_id,))
        return cursor.fetchall()
    except Error as error:
        raise RuntimeError('Gagal memuat daftar akun pembukuan.') from error
    finally:
        connection.close()


def get_journal_lines(owner_id, start_date=None, end_date=None):
    connection = get_db_connection()
    if not connection:
        raise RuntimeError('Database pembukuan tidak dapat diakses.')
    try:
        cursor = connection.cursor(dictionary=True)
        query = """
            SELECT j.id AS journal_id, j.journal_date, j.reference, j.description,
                   j.journal_type, j.cash_flow_category, a.id AS account_id,
                   a.account_code, a.account_name, a.account_type, a.normal_balance,
                   l.debit, l.credit
            FROM umkm_journals j
            JOIN umkm_journal_lines l ON l.journal_id = j.id
            JOIN umkm_accounts a ON a.id = l.account_id
            WHERE j.owner_id = %s
        """
        params = [owner_id]
        if start_date:
            query += " AND j.journal_date >= %s"
            params.append(start_date)
        if end_date:
            query += " AND j.journal_date <= %s"
            params.append(end_date)
        query += " ORDER BY j.journal_date, j.id, l.id"
        cursor.execute(query, tuple(params))
        return cursor.fetchall()
    except Error as error:
        raise RuntimeError('Gagal memuat data jurnal pembukuan.') from error
    finally:
        connection.close()


def account_totals(lines):
    totals = {}
    for line in lines:
        account_id = line['account_id']
        if account_id not in totals:
            totals[account_id] = {
                'account_id': account_id,
                'account_code': line['account_code'],
                'account_name': line['account_name'],
                'account_type': line['account_type'],
                'normal_balance': line['normal_balance'],
                'debit': ZERO,
                'credit': ZERO,
            }
        totals[account_id]['debit'] += Decimal(str(line['debit'] or 0))
        totals[account_id]['credit'] += Decimal(str(line['credit'] or 0))

    for total in totals.values():
        if total['normal_balance'] == 'debit':
            total['balance'] = total['debit'] - total['credit']
        else:
            total['balance'] = total['credit'] - total['debit']
    return sorted(totals.values(), key=lambda item: item['account_code'])
