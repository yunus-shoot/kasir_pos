from flask import Blueprint, abort, render_template, request, redirect, url_for, session, flash, jsonify
from functools import wraps
import os
import mysql.connector
from mysql.connector import Error
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
import random
import string
import uuid
from werkzeug.utils import secure_filename
from app import get_db_connection
from app.utils import (
    get_all_barang, get_barang_by_id, add_barang, update_barang, delete_barang, barang_has_related_transactions,
    get_all_kategori, add_kategori, update_kategori, delete_kategori,
    get_all_barcode_produk, get_barcode_produk_by_id, add_barcode_produk, update_barcode_produk, delete_barcode_produk,
    get_all_users, add_user, update_user, delete_user, get_user_by_id,
    get_account_owner_id, get_all_members, get_member_by_id, get_member_by_name, add_member, update_member, delete_member,
    parse_indonesian_number,
    save_transaksi, get_transactions, get_transaction_detail,
    get_dashboard_data, get_laporan_data, export_to_pdf, export_to_excel, export_barcode_produk_to_pdf,
    get_store_settings
)
from app.accounting import (
    account_totals, get_accounts, get_journal_lines, validate_journal_lines
)

main_bp = Blueprint('main', __name__)

def _parse_access_datetime(value):
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None

def _admin_access_is_valid(user_id):
    connection = get_db_connection()
    if not connection:
        return True

    try:
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            "SELECT role, is_active, active_from, active_until FROM users WHERE id = %s",
            (user_id,)
        )
        user = cursor.fetchone()
        cursor.close()
        connection.close()
        if not user or user.get('role') != 'admin':
            return True

        now = datetime.now()
        active_from = _parse_access_datetime(user.get('active_from'))
        active_until = _parse_access_datetime(user.get('active_until'))
        return (
            int(user.get('is_active') or 0) == 1
            and (not active_from or now >= active_from)
            and (not active_until or now <= active_until)
        )
    except Exception:
        try:
            connection.close()
        except Exception:
            pass
        return True

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('main.login'))
        if session.get('role') == 'umkm' and request.endpoint not in {
            'main.umkm_dashboard', 'main.umkm_accounts',
            'main.umkm_journals', 'main.umkm_ledger', 'main.umkm_reports',
            'main.umkm_profile'
        }:
            return redirect(url_for('main.umkm_dashboard'))
        if session.get('role') == 'admin' and not _admin_access_is_valid(session['user_id']):
            session.clear()
            flash('Akses admin sudah dinonaktifkan atau masa aktifnya telah berakhir.', 'danger')
            return redirect(url_for('main.login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session or session.get('role') != 'admin':
            flash('Anda tidak memiliki akses ke halaman ini!', 'danger')
            return redirect(url_for('main.dashboard'))
        return f(*args, **kwargs)
    return decorated_function


def _transaction_view_user_id():
    user_id = session.get('user_id')
    if session.get('role') == 'admin':
        return get_account_owner_id(user_id)
    return user_id


def web_admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session or session.get('role') != 'web_admin':
            flash('Anda tidak memiliki akses ke halaman ini!', 'danger')
            return redirect(url_for('main.dashboard'))
        return f(*args, **kwargs)
    return decorated_function


def umkm_required(f):
    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        if session.get('role') != 'umkm':
            flash('Halaman ini hanya untuk akun pembukuan UMKM.', 'warning')
            return redirect(url_for('main.dashboard'))
        return f(*args, **kwargs)
    return decorated_function

@main_bp.route('/')
def index():
    if 'user_id' in session:
        if session.get('role') == 'umkm':
            return redirect(url_for('main.umkm_dashboard'))
        return redirect(url_for('main.dashboard'))
    return render_template('landing.html')

@main_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'GET':
        return redirect(url_for('main.index', _anchor='login'))

    username = request.form.get('username')
    password = request.form.get('password')
    login_error = None
        
    connection = get_db_connection()
    if connection:
        cursor = connection.cursor(dictionary=True)
        cursor.execute("SELECT * FROM users WHERE username = %s AND password = %s", (username, password))
        user = cursor.fetchone()
        cursor.close()
        connection.close()
            
        if user:
            # Enforce activation and active period for Admin accounts
            if user.get('role') == 'admin':
                now = datetime.now()
                is_active = int(user.get('is_active') or 0)
                active_from = user.get('active_from')
                active_until = user.get('active_until')

                def normalize_datetime(value):
                    if not value:
                        return None
                    if isinstance(value, datetime):
                        return value
                    try:
                        return datetime.fromisoformat(str(value))
                    except Exception:
                        pass
                    try:
                        return datetime.strptime(str(value), '%Y-%m-%d %H:%M:%S')
                    except Exception:
                        pass
                    try:
                        return datetime.strptime(str(value), '%Y-%m-%d %H:%M')
                    except Exception:
                        return None

                active_from = normalize_datetime(active_from)
                active_until = normalize_datetime(active_until)

                if is_active != 1:
                    login_error = 'Akun belum diaktifkan oleh pemilik website. Hubungi pemilik untuk aktivasi.'
                elif active_from and now < active_from:
                    login_error = 'Akun belum aktif. Tanggal mulai penggunaan: ' + active_from.strftime('%Y-%m-%d %H:%M:%S')
                elif active_until and now > active_until:
                    login_error = 'Masa aktif akun telah berakhir. Hubungi pemilik untuk perpanjangan.'

            if login_error is None:
                session['user_id'] = user['id']
                session['username'] = user['username']
                session['nama_lengkap'] = user['nama_lengkap']
                session['role'] = user['role']
                session['profile_photo'] = user.get('profile_photo')
                flash(f'Selamat datang, {user["nama_lengkap"]}!', 'success')
                if user.get('role') == 'umkm':
                    return redirect(url_for('main.umkm_dashboard'))
                return redirect(url_for('main.dashboard'))
        else:
            login_error = 'Username atau password salah!'
    else:
        login_error = 'Gagal terhubung ke database!'

    return render_template('landing.html', login_error=login_error)

@main_bp.route('/logout')
def logout():
    session.clear()
    flash('Anda telah logout!', 'success')
    return redirect(url_for('main.index'))

@main_bp.route('/dashboard')
@login_required
def dashboard():
    current_user_id = session.get('user_id')
    owner_id = get_account_owner_id(current_user_id)
    store_settings = get_store_settings(owner_id)
    data = get_dashboard_data(
        user_id=_transaction_view_user_id(),
        inventory_user_id=owner_id,
        low_stock_threshold=int(store_settings.get('low_stock_threshold', 10))
    )
    return render_template('dashboard.html', data=data)


@main_bp.route('/umkm')
@main_bp.route('/umkm/')
@umkm_required
def umkm_dashboard():
    owner_id = session['user_id']
    today = datetime.now().date()
    year_start = today.replace(month=1, day=1)
    all_lines = get_journal_lines(owner_id, end_date=today)
    period_lines = [line for line in all_lines if line['journal_date'] >= year_start]
    balances = account_totals(all_lines)
    period_balances = account_totals(period_lines)
    income = sum((_statement_balance(item) for item in period_balances if item['account_type'] == 'pendapatan'), Decimal('0'))
    expenses = sum((_statement_balance(item) for item in period_balances if item['account_type'] == 'beban'), Decimal('0'))
    cash = sum(
        (item['balance'] for item in balances if item['account_code'] in {'11001', '11002'}),
        Decimal('0')
    )
    return render_template(
        'umkm_dashboard.html',
        accounts=len(get_accounts(owner_id)),
        journal_count=len({line['journal_id'] for line in all_lines}),
        cash=cash,
        income=income,
        expenses=expenses,
        profit=income - expenses,
        recent_journals=_group_journals(all_lines)[-8:][::-1],
    )


@main_bp.route('/umkm/akun-saya')
@umkm_required
def umkm_profile():
    connection = get_db_connection()
    if not connection:
        flash('Data akun tidak dapat dimuat. Silakan coba kembali.', 'danger')
        return redirect(url_for('main.umkm_dashboard'))
    try:
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            "SELECT username, nama_lengkap, role, created_at FROM users WHERE id = %s AND role = 'umkm'",
            (session['user_id'],)
        )
        user = cursor.fetchone()
        if not user:
            session.clear()
            flash('Akun UMKM tidak ditemukan. Silakan masuk kembali.', 'danger')
            return redirect(url_for('main.login'))
        return render_template('umkm_profile.html', user=user)
    except Error:
        flash('Data akun gagal dimuat. Silakan coba kembali.', 'danger')
        return redirect(url_for('main.umkm_dashboard'))
    finally:
        connection.close()


def _group_journals(lines):
    journals = {}
    for line in lines:
        journal_id = line['journal_id']
        if journal_id not in journals:
            journals[journal_id] = {
                'id': journal_id,
                'journal_date': line['journal_date'],
                'reference': line['reference'],
                'description': line['description'],
                'journal_type': line['journal_type'],
                'debit': Decimal('0'),
                'credit': Decimal('0'),
                'lines': [],
            }
        journals[journal_id]['debit'] += Decimal(str(line['debit'] or 0))
        journals[journal_id]['credit'] += Decimal(str(line['credit'] or 0))
        journals[journal_id]['lines'].append(line)
    return list(journals.values())


def _statement_balance(account):
    debit_nature = account['account_type'] in {'aset', 'beban'}
    debit = Decimal(str(account['debit'] or 0))
    credit = Decimal(str(account['credit'] or 0))
    return debit - credit if debit_nature else credit - debit


@main_bp.route('/umkm/akun', methods=['GET', 'POST'])
@umkm_required
def umkm_accounts():
    owner_id = session['user_id']
    if request.method == 'POST':
        code = request.form.get('account_code', '').strip()
        name = request.form.get('account_name', '').strip()
        account_type = request.form.get('account_type', '')
        normal_balance = request.form.get('normal_balance', '')
        if not code or not name or account_type not in {'aset', 'kewajiban', 'ekuitas', 'pendapatan', 'beban'} or normal_balance not in {'debit', 'kredit'}:
            flash('Lengkapi kode, nama, jenis akun, dan saldo normal dengan benar.', 'danger')
        else:
            connection = get_db_connection()
            if not connection:
                flash('Database pembukuan tidak dapat diakses.', 'danger')
            else:
                try:
                    cursor = connection.cursor()
                    cursor.execute("""
                        INSERT INTO umkm_accounts
                            (owner_id, account_code, account_name, account_type, normal_balance)
                        VALUES (%s, %s, %s, %s, %s)
                    """, (owner_id, code, name, account_type, normal_balance))
                    connection.commit()
                    flash('Akun berhasil ditambahkan.', 'success')
                except mysql.connector.IntegrityError:
                    connection.rollback()
                    flash('Kode akun sudah digunakan. Gunakan kode yang berbeda.', 'danger')
                except Error:
                    connection.rollback()
                    flash('Akun gagal disimpan. Coba kembali.', 'danger')
                finally:
                    connection.close()
        return redirect(url_for('main.umkm_accounts'))
    return render_template('umkm_accounts.html', accounts=get_accounts(owner_id))


@main_bp.route('/umkm/jurnal', methods=['GET', 'POST'])
@umkm_required
def umkm_journals():
    owner_id = session['user_id']
    accounts = get_accounts(owner_id)
    journal_rows = []
    if request.method == 'POST':
        journal_rows = [
            {'account_id': account_id, 'debit': debit, 'credit': credit}
            for account_id, debit, credit in zip(
                request.form.getlist('account_id'),
                request.form.getlist('debit'),
                request.form.getlist('credit')
            )
        ]
        try:
            journal_date = datetime.strptime(request.form.get('journal_date', ''), '%Y-%m-%d').date()
            description = request.form.get('description', '').strip()
            journal_type = request.form.get('journal_type', 'umum')
            flow_category = request.form.get('cash_flow_category', 'operasional')
            if not description:
                raise ValueError('Keterangan jurnal wajib diisi.')
            if journal_type not in {'saldo_awal', 'umum', 'penyesuaian'}:
                raise ValueError('Jenis jurnal tidak valid.')
            if flow_category not in {'operasional', 'investasi', 'pendanaan', 'nonkas'}:
                raise ValueError('Kategori arus kas tidak valid.')
            raw_lines = zip(
                request.form.getlist('account_id'),
                request.form.getlist('debit'),
                request.form.getlist('credit')
            )
            lines = []
            for account_id, debit_value, credit_value in raw_lines:
                if not account_id:
                    continue
                try:
                    debit = Decimal(debit_value or '0').quantize(Decimal('0.01'))
                    credit = Decimal(credit_value or '0').quantize(Decimal('0.01'))
                except InvalidOperation as error:
                    raise ValueError('Nilai debit dan kredit harus berupa angka yang valid.') from error
                lines.append({'account_id': account_id, 'debit': debit, 'credit': credit})
            lines = validate_journal_lines(lines)
            account_ids = {line['account_id'] for line in lines}
            valid_ids = {account['id'] for account in accounts}
            if not account_ids.issubset(valid_ids):
                raise ValueError('Salah satu akun tidak ditemukan atau sudah tidak aktif.')

            connection = get_db_connection()
            if not connection:
                raise RuntimeError('Database pembukuan tidak dapat diakses.')
            try:
                cursor = connection.cursor()
                cursor.execute("""
                    INSERT INTO umkm_journals
                        (owner_id, journal_date, reference, description, journal_type, cash_flow_category)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (
                    owner_id, journal_date, request.form.get('reference', '').strip() or None,
                    description, journal_type, flow_category
                ))
                journal_id = cursor.lastrowid
                cursor.executemany("""
                    INSERT INTO umkm_journal_lines (journal_id, account_id, debit, credit)
                    VALUES (%s, %s, %s, %s)
                """, [
                    (journal_id, line['account_id'], line['debit'], line['credit'])
                    for line in lines
                ])
                connection.commit()
            except Error as error:
                connection.rollback()
                raise RuntimeError('Jurnal gagal disimpan. Periksa data dan coba kembali.') from error
            finally:
                connection.close()
            flash('Jurnal berhasil disimpan dan dibukukan.', 'success')
            return redirect(url_for('main.umkm_journals'))
        except (ValueError, RuntimeError) as error:
            flash(str(error), 'danger')

    journals = _group_journals(get_journal_lines(owner_id))[-50:][::-1]
    return render_template(
        'umkm_journals.html', accounts=accounts, journals=journals,
        journal_rows=journal_rows
    )


@main_bp.route('/umkm/buku-besar')
@umkm_required
def umkm_ledger():
    owner_id = session['user_id']
    today = datetime.now().date()
    start_date = request.args.get('start_date') or today.replace(month=1, day=1).isoformat()
    end_date = request.args.get('end_date') or today.isoformat()
    try:
        start_date = datetime.strptime(start_date, '%Y-%m-%d').date().isoformat()
        end_date = datetime.strptime(end_date, '%Y-%m-%d').date().isoformat()
    except ValueError:
        flash('Tanggal periode tidak valid.', 'danger')
        start_date = today.replace(month=1, day=1).isoformat()
        end_date = today.isoformat()
    if start_date > end_date:
        flash('Tanggal mulai tidak boleh melewati tanggal akhir.', 'danger')
        start_date = today.replace(month=1, day=1).isoformat()
        end_date = today.isoformat()
    account_id = request.args.get('account_id', type=int)
    accounts = get_accounts(owner_id)
    selected_account = next((account for account in accounts if account['id'] == account_id), None)
    if account_id and not selected_account:
        flash('Akun yang dipilih tidak ditemukan.', 'danger')
        account_id = None
    all_lines = get_journal_lines(owner_id, end_date=end_date)
    lines = [
        line for line in all_lines
        if start_date <= str(line['journal_date']) <= end_date
    ]
    if account_id:
        lines = [line for line in lines if line['account_id'] == account_id]
        opening_lines = [
            line for line in all_lines
            if line['account_id'] == account_id and str(line['journal_date']) < start_date
        ]
        if selected_account['normal_balance'] == 'debit':
            opening_balance = sum(
                (Decimal(str(line['debit'] or 0)) - Decimal(str(line['credit'] or 0)) for line in opening_lines),
                Decimal('0')
            )
        else:
            opening_balance = sum(
                (Decimal(str(line['credit'] or 0)) - Decimal(str(line['debit'] or 0)) for line in opening_lines),
                Decimal('0')
            )
        balance = opening_balance
        for line in lines:
            movement = Decimal(str(line['debit'] or 0)) - Decimal(str(line['credit'] or 0))
            if selected_account['normal_balance'] == 'kredit':
                movement = -movement
            balance += movement
            line['running_balance'] = balance
    else:
        opening_balance = None
    return render_template(
        'umkm_ledger.html', accounts=accounts, lines=lines,
        account_id=account_id, selected_account=selected_account,
        opening_balance=opening_balance, start_date=start_date, end_date=end_date
    )


@main_bp.route('/umkm/laporan')
@umkm_required
def umkm_reports():
    owner_id = session['user_id']
    today = datetime.now().date()
    start_date = request.args.get('start_date') or today.replace(month=1, day=1).isoformat()
    end_date = request.args.get('end_date') or today.isoformat()
    try:
        start_date = datetime.strptime(start_date, '%Y-%m-%d').date().isoformat()
        end_date = datetime.strptime(end_date, '%Y-%m-%d').date().isoformat()
    except ValueError:
        flash('Tanggal periode tidak valid.', 'danger')
        start_date = today.replace(month=1, day=1).isoformat()
        end_date = today.isoformat()
    if start_date > end_date:
        flash('Tanggal mulai tidak boleh melewati tanggal akhir.', 'danger')
        start_date = today.replace(month=1, day=1).isoformat()
        end_date = today.isoformat()

    all_lines = get_journal_lines(owner_id, end_date=end_date)
    period_lines = [
        line for line in all_lines
        if start_date <= str(line['journal_date']) <= end_date
    ]
    previous_lines = [
        line for line in all_lines
        if str(line['journal_date']) < start_date
    ]
    all_balances = account_totals(all_lines)
    period_balances = account_totals(period_lines)
    previous_balances = account_totals(previous_lines)
    income = sum(
        (_statement_balance(item) for item in period_balances if item['account_type'] == 'pendapatan'),
        Decimal('0')
    )
    expenses = sum(
        (_statement_balance(item) for item in period_balances if item['account_type'] == 'beban'),
        Decimal('0')
    )
    prior_income = sum(
        (_statement_balance(item) for item in previous_balances if item['account_type'] == 'pendapatan'),
        Decimal('0')
    )
    prior_expenses = sum(
        (_statement_balance(item) for item in previous_balances if item['account_type'] == 'beban'),
        Decimal('0')
    )
    cash_flow = {'operasional': Decimal('0'), 'investasi': Decimal('0'), 'pendanaan': Decimal('0')}
    for line in period_lines:
        if line['account_code'] not in {'11001', '11002'}:
            continue
        if line['journal_type'] == 'saldo_awal' or line['cash_flow_category'] == 'nonkas':
            continue
        category = line['cash_flow_category']
        cash_flow[category] += Decimal(str(line['debit'] or 0)) - Decimal(str(line['credit'] or 0))

    trial_balance = []
    for item in all_balances:
        balance = item['balance']
        debit_balance = balance if item['normal_balance'] == 'debit' else -balance
        item = dict(item)
        item['trial_debit'] = max(debit_balance, Decimal('0'))
        item['trial_credit'] = max(-debit_balance, Decimal('0'))
        trial_balance.append(item)

    assets = [dict(item, balance=_statement_balance(item)) for item in all_balances if item['account_type'] == 'aset']
    liabilities = [dict(item, balance=_statement_balance(item)) for item in all_balances if item['account_type'] == 'kewajiban']
    equity = [dict(item, balance=_statement_balance(item)) for item in all_balances if item['account_type'] == 'ekuitas']
    reports = {
        'trial_balance': trial_balance,
        'trial_debit': sum((item['trial_debit'] for item in trial_balance), Decimal('0')),
        'trial_credit': sum((item['trial_credit'] for item in trial_balance), Decimal('0')),
        'income': income,
        'expenses': expenses,
        'profit': income - expenses,
        'assets': assets,
        'liabilities': liabilities,
        'equity': equity,
        'retained_earnings': prior_income - prior_expenses,
        'cash_flow': cash_flow,
    }
    beginning_by_code = {item['account_code']: item for item in previous_balances}
    ending_by_code = {item['account_code']: item for item in all_balances}
    current_assets = sum(
        (_statement_balance(item) for item in all_balances
         if item['account_type'] == 'aset' and item['account_code'].startswith('11')),
        Decimal('0')
    )
    current_liabilities = sum(
        (_statement_balance(item) for item in all_balances
         if item['account_type'] == 'kewajiban' and item['account_code'].startswith('21')),
        Decimal('0')
    )
    ending_inventory = _statement_balance(ending_by_code['11008']) if '11008' in ending_by_code else Decimal('0')
    beginning_inventory = (
        _statement_balance(beginning_by_code['11008']) if '11008' in beginning_by_code
        else ending_inventory
    )
    ending_assets = sum((_statement_balance(item) for item in all_balances if item['account_type'] == 'aset'), Decimal('0'))
    beginning_assets = sum((_statement_balance(item) for item in previous_balances if item['account_type'] == 'aset'), Decimal('0'))
    reports['asset_total'] = sum((item['balance'] for item in assets), Decimal('0'))
    reports['liability_total'] = sum((item['balance'] for item in liabilities), Decimal('0'))
    reports['equity_total'] = sum((item['balance'] for item in equity), Decimal('0'))
    net_sales = sum(
        (_statement_balance(item) for item in period_balances
         if item['account_code'] in {'41001', '42001', '42002'}),
        Decimal('0')
    )
    cost_of_sales = sum(
        (_statement_balance(item) for item in period_balances
         if item['account_code'] in {'51015', '51101'}),
        Decimal('0')
    )
    average_inventory = (beginning_inventory + ending_inventory) / 2
    average_assets = (beginning_assets + ending_assets) / 2
    reports['ratios'] = [
        ('Rasio lancar', current_assets / current_liabilities if current_liabilities else None, 'kali'),
        ('Rasio utang terhadap aset', reports['liability_total'] / reports['asset_total'] * 100 if reports['asset_total'] else None, '%'),
        ('Perputaran persediaan', cost_of_sales / average_inventory if average_inventory else None, 'kali'),
        ('Perputaran total aset', net_sales / average_assets if average_assets else None, 'kali'),
    ]
    reports['total_equity'] = (
        reports['equity_total'] + reports['retained_earnings'] + reports['profit']
    )
    reports['cash_flow_total'] = sum(cash_flow.values(), Decimal('0'))
    return render_template(
        'umkm_reports.html', reports=reports,
        start_date=start_date, end_date=end_date
    )

@main_bp.route('/transaksi', methods=['GET', 'POST'])
@login_required
def transaksi():
    owner_id = get_account_owner_id(session.get('user_id'))
    
    if request.method == 'POST':
        # Handle add to cart via AJAX
        data = request.get_json() or {}
        
        barang_id = data.get('barang_id')
        try:
            jumlah = int(data.get('jumlah', 1))
        except (TypeError, ValueError):
            return jsonify({'success': False, 'message': 'Jumlah barang tidak valid.'}), 400
        
        if barang_id is None:
            return jsonify({'success': False, 'message': 'ID barang tidak diberikan.'})
        
        barang = get_barang_by_id(barang_id, user_id=owner_id)
        if barang:
            stok = int(barang.get('stok') or 0)
            cart = session.get('cart', [])
            cart_item = next((item for item in cart if str(item['id']) == str(barang_id)), None)
            requested_quantity = (int(cart_item['jumlah']) if cart_item else 0) + jumlah
            if stok <= 0:
                return jsonify({
                    'success': False,
                    'message': f"Stok {barang['nama_barang']} habis. Segera isi kembali sebelum menambahkan ke keranjang."
                }), 409
            if jumlah <= 0 or requested_quantity > stok:
                return jsonify({
                    'success': False,
                    'message': f"Stok {barang['nama_barang']} tidak mencukupi. Stok tersedia: {stok}."
                }), 409

            if cart_item:
                cart_item['jumlah'] = requested_quantity
                cart_item['subtotal'] = requested_quantity * cart_item['harga_jual']
                cart_item['stok'] = stok
            else:
                cart.append({
                    'id': barang['id'],
                    'kode_barang': barang['kode_barang'],
                    'nama_barang': barang['nama_barang'],
                    'harga_jual': float(barang['harga_jual']),
                    'jumlah': jumlah,
                    'subtotal': float(barang['harga_jual']) * jumlah,
                    'stok': stok
                })
            
            session['cart'] = cart
            session.modified = True
            return jsonify({'success': True, 'cart': cart})

        return jsonify({'success': False, 'message': 'Barang tidak ditemukan atau gagal terhubung ke database.'})
    
    # Clear cart for new transaction
    if request.method == 'GET' and request.args.get('clear_cart'):
        session.pop('cart', None)
        session.modified = True
    
    barang_list = get_all_barang(user_id=owner_id)
    cart = session.get('cart', [])
    return render_template('transaksi.html', barang_list=barang_list, cart=cart)

@main_bp.route('/update-cart', methods=['POST'])
@login_required
def update_cart():
    data = request.get_json()
    action = data.get('action')
    barang_id = data.get('barang_id')

    try:
        barang_id = int(barang_id)
    except (TypeError, ValueError):
        return jsonify({'success': False, 'message': 'ID barang tidak valid.'}), 400
    
    cart = session.get('cart', [])
    
    if action == 'update':
        try:
            jumlah = max(1, int(data.get('jumlah', 1)))
        except (TypeError, ValueError):
            return jsonify({'success': False, 'message': 'Jumlah barang tidak valid.'}), 400
        for item in cart:
            if str(item['id']) == str(barang_id):
                barang = get_barang_by_id(barang_id, user_id=get_account_owner_id(session.get('user_id')))
                if not barang:
                    return jsonify({'success': False, 'message': 'Barang tidak ditemukan.'}), 404
                stok = int(barang.get('stok') or 0)
                current_quantity = int(item['jumlah'])
                if jumlah > stok and jumlah > current_quantity:
                    if stok <= 0:
                        return jsonify({
                            'success': False,
                            'message': f"Stok {barang['nama_barang']} habis. Segera isi kembali."
                        }), 409
                    return jsonify({
                        'success': False,
                        'message': f"Stok {barang['nama_barang']} tidak mencukupi. Stok tersedia: {stok}."
                    }), 409
                item['jumlah'] = jumlah
                item['subtotal'] = item['jumlah'] * item['harga_jual']
                item['stok'] = stok
                break
    elif action == 'remove':
        cart = [item for item in cart if item['id'] != barang_id]
    
    session['cart'] = cart
    session.modified = True
    
    total = sum(item['subtotal'] for item in cart)
    return jsonify({'success': True, 'cart': cart, 'total': total})

@main_bp.route('/checkout', methods=['POST'])
@login_required
def checkout():
    return_to = 'scanner' if request.form.get('return_to') == 'scanner' else 'transaksi'
    checkout_page = url_for(f'main.{return_to}')
    if 'cart' not in session or not session['cart']:
        flash('Keranjang belanja kosong!', 'warning')
        return redirect(checkout_page)
    
    metode_pembayaran = request.form.get('metode_pembayaran')
    try:
        jumlah_bayar = parse_indonesian_number(request.form.get('jumlah_bayar', 0))
    except (TypeError, ValueError):
        flash('Jumlah pembayaran tidak valid!', 'danger')
        return redirect(checkout_page)
    nama_pelanggan = request.form.get('nama_pelanggan', '').strip() or None

    cart = session.get('cart', [])
    subtotal = sum(float(item['subtotal']) for item in cart)
    member_id = None
    diskon_persen = 0.0
    diskon_nominal = 0.0
    submitted_member_id = request.form.get('member_id', '').strip()
    if submitted_member_id:
        try:
            member_id = int(submitted_member_id)
        except ValueError:
            flash('Data member tidak valid.', 'danger')
            return redirect(checkout_page)
        member = get_member_by_id(member_id, get_account_owner_id(session['user_id']), active_only=True)
        if not member:
            flash('Member tidak ditemukan atau sudah tidak aktif. Periksa nama pelanggan.', 'warning')
            return redirect(checkout_page)
        nama_pelanggan = member['nama']
        try:
            diskon_input = float(request.form.get('diskon_persen', member['diskon_persen']))
        except (TypeError, ValueError):
            diskon_input = 0.0
        batas_diskon = float(member['diskon_persen'])
        diskon_persen = max(0.0, min(diskon_input, batas_diskon, 100.0))
        diskon_nominal = round(subtotal * diskon_persen / 100, 2)

    total = round(subtotal - diskon_nominal, 2)
    
    if jumlah_bayar < total:
        flash('Jumlah pembayaran kurang!', 'danger')
        return redirect(checkout_page)
    
    kembalian = jumlah_bayar - total
    
    # Generate kode transaksi
    kode_transaksi = 'TRX-' + datetime.now().strftime('%Y%m%d') + ''.join(random.choices(string.digits, k=6))
    
    # Save transaction
    result = save_transaksi(
        kode_transaksi, session['user_id'], total, metode_pembayaran, jumlah_bayar,
        kembalian, cart, nama_pelanggan=nama_pelanggan, member_id=member_id,
        diskon_persen=diskon_persen, diskon_nominal=diskon_nominal
    )
    
    if result:
        # Update stock
        connection = get_db_connection()
        if connection:
            cursor = connection.cursor()
            for item in cart:
                cursor.execute("UPDATE barang SET stok = stok - %s WHERE id = %s", (item['jumlah'], item['id']))
            connection.commit()
            cursor.close()
            connection.close()
        
        session.pop('cart', None)
        session.modified = True
        
        flash(f'Transaksi berhasil! Kode: {kode_transaksi}, Kembalian: Rp {kembalian:,.0f}', 'success')
        return redirect(url_for('main.cetak_struk', kode=kode_transaksi))
    else:
        flash('Gagal menyimpan transaksi!', 'danger')
        return redirect(checkout_page)

@main_bp.route('/cetak-struk/<kode>')
@login_required
def cetak_struk(kode):
    transaction = get_transaction_detail(kode, user_id=_transaction_view_user_id())
    if not transaction:
        flash('Transaksi tidak ditemukan!', 'danger')
        return redirect(url_for('main.dashboard'))
    
    owner_id = get_account_owner_id(session.get('user_id'))
    settings_data = get_store_settings(owner_id)
    
    return render_template('struk.html', transaction=transaction, settings=settings_data)


@main_bp.route('/admin-web', methods=['GET', 'POST'])
@login_required
@web_admin_required
def admin_web():
    # Provide global overview and user access management for web admin
    connection = get_db_connection()
    stats = {'users': 0, 'products': 0, 'transactions': 0}
    users = []

    if connection:
        cursor = connection.cursor(dictionary=True)

        # Ensure user access columns exist (migrations)
        try:
            cursor.execute("SHOW COLUMNS FROM users LIKE 'active_from'")
            if cursor.fetchone() is None:
                cursor.execute("ALTER TABLE users ADD COLUMN active_from DATETIME DEFAULT NULL")
        except Exception:
            pass
        try:
            cursor.execute("SHOW COLUMNS FROM users LIKE 'active_until'")
            if cursor.fetchone() is None:
                cursor.execute("ALTER TABLE users ADD COLUMN active_until DATETIME DEFAULT NULL")
        except Exception:
            pass
        try:
            cursor.execute("SHOW COLUMNS FROM users LIKE 'duration_days'")
            if cursor.fetchone() is None:
                cursor.execute("ALTER TABLE users ADD COLUMN duration_days INT DEFAULT NULL")
        except Exception:
            pass
        try:
            cursor.execute("SHOW COLUMNS FROM users LIKE 'is_active'")
            if cursor.fetchone() is None:
                cursor.execute("ALTER TABLE users ADD COLUMN is_active TINYINT(1) DEFAULT 0")
        except Exception:
            pass
        connection.commit()

        # handle POST updates from admin web form (individual or bulk)
        if request.method == 'POST':
            # Create audit_logs table if missing
            try:
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS audit_logs (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        actor_id INT,
                        target_user_id INT,
                        action VARCHAR(100),
                        details TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                connection.commit()
            except Exception:
                pass

            # Create admin via Admin Web
            if request.form.get('create_admin'):
                uname = request.form.get('username')
                pwd = request.form.get('password')
                nama = request.form.get('nama_lengkap')
                try:
                    # use helper to add user scoped to current owner admin
                    added = add_user(uname, pwd, nama, 'admin', owner_id=session.get('user_id'))
                    if added:
                        # ensure account starts inactive
                        try:
                            cursor.execute("UPDATE users SET is_active=0, active_from=NULL, active_until=NULL, duration_days=NULL WHERE username=%s", (uname,))
                            cursor.execute("INSERT INTO audit_logs (actor_id,target_user_id,action,details) VALUES (%s,(SELECT id FROM users WHERE username=%s),'create_admin','Created admin account (inactive)')", (session.get('user_id'), uname))
                            connection.commit()
                        except Exception:
                            pass
                        flash('Admin baru berhasil dibuat. Akun dalam keadaan non-aktif.', 'success')
                    else:
                        flash('Gagal membuat admin baru.', 'danger')
                except Exception as e:
                    flash('Gagal membuat admin: ' + str(e), 'danger')
                # after handling create_admin, reload list
                try:
                    cursor.execute("SELECT id, username, nama_lengkap, role, active_from, active_until, duration_days, is_active FROM users WHERE role = 'admin' ORDER BY id DESC")
                    users = cursor.fetchall()
                except Exception:
                    users = []
                cursor.close()
                connection.close()
                return render_template('admin_web.html', stats=stats, users=users)

            # Bulk actions
            bulk_action = request.form.get('bulk_action')
            if bulk_action:
                selected = request.form.getlist('selected_users')
                extend_days = int(request.form.get('extend_days') or 0)
                for uid in selected:
                    try:
                        if bulk_action == 'activate':
                            # if extend_days provided, set active_from now and compute active_until
                            if extend_days and extend_days > 0:
                                from datetime import datetime as _dt
                                base = _dt.now()
                                new_until = base + timedelta(days=extend_days)
                                cursor.execute("UPDATE users SET is_active=1, active_from=%s, active_until=%s WHERE id=%s", (base.strftime('%Y-%m-%d %H:%M:%S'), new_until.strftime('%Y-%m-%d %H:%M:%S'), uid))
                                cursor.execute("INSERT INTO audit_logs (actor_id,target_user_id,action,details) VALUES (%s,%s,%s,%s)",
                                               (session.get('user_id'), uid, 'bulk_activate_timed', f'Activated with {extend_days} days via Admin Web'))
                            else:
                                cursor.execute("UPDATE users SET is_active=1 WHERE id=%s", (uid,))
                                cursor.execute("INSERT INTO audit_logs (actor_id,target_user_id,action,details) VALUES (%s,%s,%s,%s)",
                                               (session.get('user_id'), uid, 'bulk_activate', 'Activated account via Admin Web'))
                        elif bulk_action == 'deactivate':
                            cursor.execute("UPDATE users SET is_active=0 WHERE id=%s", (uid,))
                            cursor.execute("INSERT INTO audit_logs (actor_id,target_user_id,action,details) VALUES (%s,%s,%s,%s)",
                                           (session.get('user_id'), uid, 'bulk_deactivate', 'Deactivated account via Admin Web'))
                        elif bulk_action == 'extend' and extend_days > 0:
                            # extend active_until by extend_days (or set from now if null)
                            cursor.execute("SELECT active_until FROM users WHERE id=%s", (uid,))
                            row = cursor.fetchone()
                            cur_until = row.get('active_until') if row else None
                            from datetime import datetime as _dt
                            base = _dt.now() if not cur_until else cur_until
                            new_until = base + timedelta(days=extend_days)
                            cursor.execute("UPDATE users SET active_until=%s, is_active=1 WHERE id=%s", (new_until.strftime('%Y-%m-%d %H:%M:%S'), uid))
                            cursor.execute("INSERT INTO audit_logs (actor_id,target_user_id,action,details) VALUES (%s,%s,%s,%s)",
                                           (session.get('user_id'), uid, 'bulk_extend', f'Extended by {extend_days} days via Admin Web'))
                    except Exception:
                        continue
                connection.commit()
                flash('Bulk action berhasil dijalankan.', 'success')
            else:
                # individual update
                user_id = request.form.get('user_id')
                # parse datetime-local values to MySQL DATETIME format
                def parse_dt_local(val):
                    if not val:
                        return None
                    try:
                        s = val.replace('T', ' ')
                        if len(s) == 16:
                            s = s + ':00'
                        # simple validation: attempt to parse
                        datetime.strptime(s, '%Y-%m-%d %H:%M:%S')
                        return s
                    except Exception:
                        return None

                active_from = parse_dt_local(request.form.get('active_from'))
                active_until = parse_dt_local(request.form.get('active_until'))
                duration_days = request.form.get('duration_days') or None
                is_active = 1 if request.form.get('is_active') else 0

                # If activating without an explicit start, use now as active_from
                if is_active == 1 and not active_from:
                    af_dt_obj = datetime.now()
                    active_from = af_dt_obj.strftime('%Y-%m-%d %H:%M:%S')

                # auto-compute active_until if duration_days provided and active_from exists
                if duration_days and active_from:
                    try:
                        af_dt = datetime.strptime(active_from, '%Y-%m-%d %H:%M:%S')
                        au_dt = af_dt + timedelta(days=int(duration_days))
                        active_until = au_dt.strftime('%Y-%m-%d %H:%M:%S')
                    except Exception:
                        active_until = None

                try:
                    if user_id:
                        cursor.execute(
                            "UPDATE users SET active_from=%s, active_until=%s, duration_days=%s, is_active=%s WHERE id=%s",
                            (active_from, active_until, duration_days, is_active, user_id)
                        )
                        cursor.execute("INSERT INTO audit_logs (actor_id,target_user_id,action,details) VALUES (%s,%s,%s,%s)",
                                       (session.get('user_id'), user_id, 'update_access', f'Updated access: from={active_from}, until={active_until}, days={duration_days}, active={is_active}'))
                        connection.commit()
                        flash('Pengaturan akses pengguna diperbarui.', 'success')
                except Exception as e:
                    flash('Gagal memperbarui pengguna: ' + str(e), 'danger')

        # gather stats
        try:
            cursor.execute('SELECT COUNT(*) as c FROM users')
            stats['users'] = cursor.fetchone().get('c', 0)
        except Exception:
            stats['users'] = 0
        try:
            cursor.execute('SELECT COUNT(*) as c FROM barang')
            stats['products'] = cursor.fetchone().get('c', 0)
        except Exception:
            stats['products'] = 0
        try:
            cursor.execute('SELECT COUNT(*) as c FROM transaksi')
            stats['transactions'] = cursor.fetchone().get('c', 0)
        except Exception:
            stats['transactions'] = 0

        # fetch users for management table
        try:
            # Only show admin accounts — system manages kasir under Admin
            cursor.execute("SELECT id, username, nama_lengkap, role, active_from, active_until, duration_days, is_active FROM users WHERE role = 'admin' ORDER BY id DESC")
            users = cursor.fetchall()
        except Exception:
            users = []

        cursor.close()
        connection.close()

    return render_template('admin_web.html', stats=stats, users=users)


@main_bp.route('/api/admin/toggle-user', methods=['POST'])
@web_admin_required
def api_toggle_user():
    """Toggle user active status via AJAX"""
    try:
        user_id = request.json.get('user_id')
        is_active = request.json.get('is_active', 0)
        
        connection = get_db_connection()
        if connection:
            cursor = connection.cursor(dictionary=True)
            
            # If activating, set active_from to now if not set
            if is_active == 1:
                cursor.execute("SELECT active_from FROM users WHERE id=%s", (user_id,))
                user = cursor.fetchone()
                if not user or not user.get('active_from'):
                    active_from = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    cursor.execute("UPDATE users SET is_active=1, active_from=%s WHERE id=%s", 
                                 (active_from, user_id))
                else:
                    cursor.execute("UPDATE users SET is_active=1 WHERE id=%s", (user_id,))
            else:
                cursor.execute("UPDATE users SET is_active=0 WHERE id=%s", (user_id,))
            
            cursor.execute("INSERT INTO audit_logs (actor_id,target_user_id,action,details) VALUES (%s,%s,%s,%s)",
                         (session.get('user_id'), user_id, 'toggle_status', f'Status set to: {is_active}'))
            
            connection.commit()
            
            # Return updated user data
            cursor.execute("SELECT id, username, nama_lengkap, role, active_from, active_until, duration_days, is_active FROM users WHERE id=%s", (user_id,))
            user = cursor.fetchone()
            cursor.close()
            connection.close()
            
            if user:
                return jsonify({
                    'success': True,
                    'user': {
                        'id': user['id'],
                        'username': user['username'],
                        'nama_lengkap': user['nama_lengkap'],
                        'active_from': user['active_from'],
                        'active_until': user['active_until'],
                        'duration_days': user['duration_days'],
                        'is_active': user['is_active']
                    }
                })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    
    return jsonify({'success': False, 'error': 'Gagal update'}), 400


@main_bp.route('/api/admin/bulk-action', methods=['POST'])
@web_admin_required
def api_bulk_action():
    """Handle bulk actions via AJAX"""
    try:
        data = request.json
        action = data.get('action')
        selected_users = data.get('selected_users', [])
        extend_days = int(data.get('extend_days', 0))
        
        if not selected_users:
            return jsonify({'success': False, 'error': 'Tidak ada pengguna yang dipilih'}), 400
        
        connection = get_db_connection()
        if connection:
            cursor = connection.cursor(dictionary=True)
            
            for uid in selected_users:
                try:
                    if action == 'deactivate':
                        cursor.execute("UPDATE users SET is_active=0 WHERE id=%s", (uid,))
                        cursor.execute("INSERT INTO audit_logs (actor_id,target_user_id,action,details) VALUES (%s,%s,%s,%s)",
                                     (session.get('user_id'), uid, 'bulk_deactivate', 'Deactivated via API'))
                    elif action == 'activate':
                        active_from = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                        if extend_days > 0:
                            active_until = (datetime.now() + timedelta(days=extend_days)).strftime('%Y-%m-%d %H:%M:%S')
                            cursor.execute("UPDATE users SET is_active=1, active_from=%s, active_until=%s, duration_days=%s WHERE id=%s",
                                         (active_from, active_until, extend_days, uid))
                        else:
                            cursor.execute("UPDATE users SET is_active=1, active_from=%s WHERE id=%s",
                                         (active_from, uid))
                        cursor.execute("INSERT INTO audit_logs (actor_id,target_user_id,action,details) VALUES (%s,%s,%s,%s)",
                                     (session.get('user_id'), uid, 'bulk_activate', f'Activated for {extend_days} days via API'))
                    elif action == 'extend' and extend_days > 0:
                        cursor.execute("SELECT active_until FROM users WHERE id=%s", (uid,))
                        row = cursor.fetchone()
                        cur_until = row.get('active_until') if row else None
                        base = datetime.now() if not cur_until else cur_until
                        new_until = (base + timedelta(days=extend_days)).strftime('%Y-%m-%d %H:%M:%S')
                        cursor.execute("UPDATE users SET active_until=%s, is_active=1 WHERE id=%s",
                                     (new_until, uid))
                        cursor.execute("INSERT INTO audit_logs (actor_id,target_user_id,action,details) VALUES (%s,%s,%s,%s)",
                                     (session.get('user_id'), uid, 'bulk_extend', f'Extended by {extend_days} days via API'))
                except Exception:
                    continue
            
            connection.commit()
            
            # Return updated users list
            cursor.execute("SELECT id, username, nama_lengkap, role, active_from, active_until, duration_days, is_active FROM users WHERE role='admin' ORDER BY id DESC")
            users = cursor.fetchall()
            cursor.close()
            connection.close()
            
            return jsonify({
                'success': True,
                'message': 'Aksi massal berhasil dijalankan',
                'users': [
                    {
                        'id': u['id'],
                        'username': u['username'],
                        'nama_lengkap': u['nama_lengkap'],
                        'active_from': u['active_from'],
                        'active_until': u['active_until'],
                        'duration_days': u['duration_days'],
                        'is_active': u['is_active']
                    } for u in users
                ]
            })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    
    return jsonify({'success': False, 'error': 'Gagal'}), 400


@main_bp.route('/api/admin/update-dates', methods=['POST'])
@web_admin_required
def api_update_dates():
    """Update user dates via AJAX"""
    try:
        data = request.json
        user_id = data.get('user_id')
        active_from = data.get('active_from')
        duration_days = data.get('duration_days')
        
        connection = get_db_connection()
        if connection:
            cursor = connection.cursor(dictionary=True)
            
            # Auto-compute active_until if duration provided
            active_until = None
            if active_from and duration_days:
                try:
                    af_dt = datetime.fromisoformat(active_from.replace('T', ' '))
                    au_dt = af_dt + timedelta(days=int(duration_days))
                    active_until = au_dt.strftime('%Y-%m-%d %H:%M:%S')
                except Exception:
                    pass
            
            cursor.execute("UPDATE users SET active_from=%s, active_until=%s, duration_days=%s WHERE id=%s",
                         (active_from, active_until, duration_days, user_id))
            cursor.execute("INSERT INTO audit_logs (actor_id,target_user_id,action,details) VALUES (%s,%s,%s,%s)",
                         (session.get('user_id'), user_id, 'update_dates', f'Updated dates and duration via API'))
            
            connection.commit()
            
            # Return updated user
            cursor.execute("SELECT id, username, nama_lengkap, role, active_from, active_until, duration_days, is_active FROM users WHERE id=%s", (user_id,))
            user = cursor.fetchone()
            cursor.close()
            connection.close()
            
            if user:
                return jsonify({
                    'success': True,
                    'user': {
                        'id': user['id'],
                        'active_from': user['active_from'],
                        'active_until': user['active_until'],
                        'duration_days': user['duration_days']
                    }
                })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    
    return jsonify({'success': False, 'error': 'Gagal update'}), 400

@main_bp.route('/barang', methods=['GET', 'POST'])
@login_required
def barang():
    current_user_id = session.get('user_id')
    owner_id = get_account_owner_id(current_user_id)
    is_admin = session.get('role') == 'admin'
    if not is_admin and session.get('role') != 'kasir':
        abort(403)
    if request.method == 'POST':
        action = request.form.get('action')
        if not is_admin and action != 'add':
            abort(403)
        
        if action == 'add':
            kode_barang = request.form.get('kode_barang')
            nama_barang = request.form.get('nama_barang', '').strip().upper()
            kategori_id = request.form.get('kategori_id')
            try:
                harga_beli = parse_indonesian_number(request.form.get('harga_beli'))
                harga_jual = parse_indonesian_number(request.form.get('harga_jual'))
            except (TypeError, ValueError):
                flash('Harga beli dan harga jual harus berupa angka yang valid.', 'danger')
                return redirect(url_for('main.barang'))
            stok = request.form.get('stok')
            barcode = request.form.get('barcode')
            deskripsi = request.form.get('deskripsi')

            allowed_categories = {str(category['id']) for category in get_all_kategori(owner_id)}
            if str(kategori_id) not in allowed_categories:
                flash('Kategori tidak valid untuk akun Anda.', 'danger')
                return redirect(url_for('main.barang'))

            existing_connection = get_db_connection()
            duplicate_code = False
            if existing_connection:
                existing_cursor = existing_connection.cursor()
                existing_cursor.execute(
                    "SELECT id FROM barang WHERE kode_barang = %s AND user_id = %s LIMIT 1",
                    (kode_barang, owner_id)
                )
                duplicate_code = existing_cursor.fetchone() is not None
                existing_cursor.close()
                existing_connection.close()

            if duplicate_code:
                flash('Kode produk tersebut sudah digunakan di katalog Anda.', 'danger')
                return redirect(url_for('main.barang'))
            
            result = add_barang(kode_barang, nama_barang, kategori_id, harga_beli, harga_jual, stok, barcode, deskripsi, user_id=owner_id)
            if result:
                flash('Barang berhasil ditambahkan!', 'success')
            else:
                flash('Gagal menambahkan barang!', 'danger')
        
        elif action == 'edit':
            barang_id = request.form.get('barang_id')
            kode_barang = request.form.get('kode_barang')
            nama_barang = request.form.get('nama_barang', '').strip().upper()
            kategori_id = request.form.get('kategori_id')
            try:
                harga_beli = parse_indonesian_number(request.form.get('harga_beli'))
                harga_jual = parse_indonesian_number(request.form.get('harga_jual'))
            except (TypeError, ValueError):
                flash('Harga beli dan harga jual harus berupa angka yang valid.', 'danger')
                return redirect(url_for('main.barang'))
            stok = request.form.get('stok')
            barcode = request.form.get('barcode')
            deskripsi = request.form.get('deskripsi')
            
            result = update_barang(barang_id, kode_barang, nama_barang, kategori_id, harga_beli, harga_jual, stok, barcode, deskripsi, user_id=owner_id)
            if result:
                flash('Barang berhasil diperbarui!', 'success')
            else:
                flash('Gagal memperbarui barang!', 'danger')
        
        elif action == 'delete':
            barang_id = request.form.get('barang_id')
            # Verify item exists and belongs to current user before deletion
            barang_row = get_barang_by_id(barang_id, user_id=owner_id)
            if not barang_row:
                flash('Barang tidak ditemukan atau bukan milik Anda.', 'danger')
            elif barang_has_related_transactions(barang_id):
                flash('Barang tidak bisa dihapus karena sudah digunakan di transaksi. Batalkan atau hapus transaksi terkait terlebih dahulu.', 'danger')
            else:
                result = delete_barang(barang_id, user_id=owner_id)
                if result:
                    flash('Barang berhasil dihapus!', 'success')
                else:
                    # Likely database error or unexpected constraint issue
                    flash('Gagal menghapus barang! Periksa apakah barang terkait data lain.', 'danger')
        
        return redirect(url_for('main.barang'))
    
    barang_list = get_all_barang(user_id=owner_id)
    kategori_list = get_all_kategori(user_id=owner_id)
    return render_template('barang.html', barang_list=barang_list, kategori_list=kategori_list, is_admin=is_admin)

@main_bp.route('/barcode-produk', methods=['GET', 'POST'])
@login_required
@admin_required
def barcode_produk():
    current_user_id = session.get('user_id')
    search_query = request.args.get('search', '').strip()

    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'add':
            nama_barang = request.form.get('nama_barang', '').strip().upper()
            kategori_id = request.form.get('kategori_id', type=int)
            deskripsi = request.form.get('deskripsi', '').strip() or None
            try:
                harga_beli = parse_indonesian_number(request.form.get('harga_beli', ''))
                harga_jual = parse_indonesian_number(request.form.get('harga_jual', ''))
                stok = int(request.form.get('stok', ''))
                jumlah_label = int(request.form.get('jumlah_label', 1))
            except (TypeError, ValueError):
                harga_beli = harga_jual = -1
                stok = -1
                jumlah_label = 0

            if (not nama_barang or len(nama_barang) > 200 or kategori_id is None
                    or harga_beli < 0 or harga_jual < 0 or stok < 0
                    or jumlah_label < 1 or jumlah_label > 1000):
                flash('Lengkapi data produk dengan benar. Stok tidak boleh negatif dan jumlah label harus 1 sampai 1000.', 'danger')
                return redirect(url_for('main.barcode_produk', search=search_query))

            result = add_barcode_produk(
                nama_barang, kategori_id, harga_beli, harga_jual, stok,
                jumlah_label, deskripsi, user_id=current_user_id
            )
            if result:
                flash(f'Produk berhasil dibuat dengan ID barcode {result}.', 'success')
            else:
                flash('Produk dan barcode gagal disimpan. Periksa kategori dan kode yang digunakan.', 'danger')

        elif action == 'edit':
            barcode_id = request.form.get('barcode_id')
            nama_barang = request.form.get('nama_barang', '').strip().upper()
            kategori_id = request.form.get('kategori_id')
            try:
                harga_beli = parse_indonesian_number(request.form.get('harga_beli'))
                harga_jual = parse_indonesian_number(request.form.get('harga_jual'))
            except (TypeError, ValueError):
                flash('Harga beli dan harga jual harus berupa angka yang valid.', 'danger')
                return redirect(url_for('main.barcode_produk', search=search_query))
            stok = request.form.get('stok', 0)
            jumlah_label = request.form.get('jumlah_label', 1)
            deskripsi = request.form.get('deskripsi')

            result = update_barcode_produk(barcode_id, nama_barang, kategori_id, harga_beli, harga_jual, stok, jumlah_label, deskripsi, user_id=current_user_id)
            if result:
                flash('Barcode produk berhasil diperbarui!', 'success')
            else:
                flash('Gagal memperbarui barcode produk!', 'danger')

        elif action == 'delete':
            barcode_id = request.form.get('barcode_id')
            result = delete_barcode_produk(barcode_id, user_id=current_user_id)
            if result:
                flash('Barcode produk berhasil dihapus!', 'success')
            else:
                flash('Gagal menghapus barcode produk!', 'danger')

        return redirect(url_for('main.barcode_produk', search=search_query))

    barcode_list = get_all_barcode_produk(user_id=current_user_id, search_query=search_query)
    kategori_list = get_all_kategori(user_id=current_user_id)
    return render_template(
        'barcode_produk.html', barcode_list=barcode_list, kategori_list=kategori_list,
        search_query=search_query
    )


@main_bp.route('/barcode-produk/<int:barcode_id>/pdf')
@login_required
@admin_required
def download_barcode_produk_pdf(barcode_id):
    current_user_id = session.get('user_id')
    barcode_product = get_barcode_produk_by_id(barcode_id, user_id=current_user_id)
    if not barcode_product:
        abort(404)
    return export_barcode_produk_to_pdf(barcode_product)

@main_bp.route('/kategori', methods=['GET', 'POST'])
@login_required
@admin_required
def kategori():
    current_user_id = session.get('user_id')
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'add':
            nama_kategori = request.form.get('nama_kategori', '').strip().upper()
            deskripsi = request.form.get('deskripsi')
            
            result = add_kategori(nama_kategori, deskripsi, user_id=current_user_id)
            if result:
                flash('Kategori berhasil ditambahkan!', 'success')
            else:
                flash('Gagal menambahkan kategori!', 'danger')
        
        elif action == 'edit':
            kategori_id = request.form.get('kategori_id')
            nama_kategori = request.form.get('nama_kategori', '').strip().upper()
            deskripsi = request.form.get('deskripsi')
            
            result = update_kategori(kategori_id, nama_kategori, deskripsi, user_id=current_user_id)
            if result:
                flash('Kategori berhasil diperbarui!', 'success')
            else:
                flash('Gagal memperbarui kategori!', 'danger')
        
        elif action == 'delete':
            kategori_id = request.form.get('kategori_id')
            result = delete_kategori(kategori_id, user_id=current_user_id)
            if result:
                flash('Kategori berhasil dihapus!', 'success')
            else:
                flash('Gagal menghapus kategori!', 'danger')
        
        return redirect(url_for('main.kategori'))
    
    kategori_list = get_all_kategori(user_id=current_user_id)
    return render_template('kategori.html', kategori_list=kategori_list)


@main_bp.route('/member', methods=['GET', 'POST'])
@login_required
@admin_required
def member():
    owner_id = get_account_owner_id(session.get('user_id'))
    if request.method == 'POST':
        action = request.form.get('action')
        nama = request.form.get('nama', '').strip()
        telepon = request.form.get('telepon', '').strip()
        email = request.form.get('email', '').strip()
        alamat = request.form.get('alamat', '').strip()
        try:
            diskon_persen = float(request.form.get('diskon_persen', 0))
        except (TypeError, ValueError):
            diskon_persen = -1

        if action in ('add', 'edit') and (not nama or not telepon or not 0 <= diskon_persen <= 100):
            flash('Nama, nomor telepon, dan diskon 0 sampai 100% wajib diisi dengan benar.', 'danger')
            return redirect(url_for('main.member'))

        if action == 'add':
            result = add_member(owner_id, nama, telepon, email, alamat, diskon_persen)
            flash('Member berhasil ditambahkan!' if result else 'Gagal menambahkan member.', 'success' if result else 'danger')
        elif action == 'edit':
            try:
                member_id = int(request.form.get('member_id', ''))
            except ValueError:
                member_id = 0
            aktif = 1 if request.form.get('aktif') else 0
            result = update_member(member_id, owner_id, nama, telepon, email, alamat, diskon_persen, aktif)
            flash('Data member berhasil diperbarui!' if result else 'Gagal memperbarui member.', 'success' if result else 'danger')
        elif action == 'delete':
            try:
                member_id = int(request.form.get('member_id', ''))
            except ValueError:
                member_id = 0
            result = delete_member(member_id, owner_id)
            flash('Member berhasil dihapus!' if result else 'Gagal menghapus member.', 'success' if result else 'danger')
        return redirect(url_for('main.member'))

    return render_template('member.html', member_list=get_all_members(owner_id))


@main_bp.route('/api/member-lookup')
@login_required
def member_lookup():
    nama = request.args.get('nama', '').strip()
    if not nama:
        return jsonify({'success': False})
    found_member = get_member_by_name(nama, get_account_owner_id(session.get('user_id')))
    if not found_member:
        return jsonify({'success': False})
    return jsonify({
        'success': True,
        'member': {
            'id': found_member['id'],
            'nama': found_member['nama'],
            'diskon_persen': float(found_member['diskon_persen'])
        }
    })

@main_bp.route('/scanner')
@login_required
def scanner():
    cart = session.get('cart', [])
    return render_template('scanner.html', cart=cart)

@main_bp.route('/scan-barcode', methods=['POST'])
@login_required
def scan_barcode():
    data = request.get_json()
    barcode = data.get('barcode', '')
    
    connection = get_db_connection()
    if connection:
        cursor = connection.cursor(dictionary=True)
        cursor.execute("""
            SELECT b.id, b.kode_barang, b.nama_barang, b.harga_jual, b.stok
            FROM barang b
            WHERE (b.barcode = %s OR b.kode_barang = %s)
              AND b.user_id = (
                  SELECT CASE
                      WHEN u.role = 'admin' THEN u.id
                      ELSE COALESCE(NULLIF(u.owner_id, 0), u.id)
                  END
                  FROM users u
                  WHERE u.id = %s
              )
            LIMIT 1
        """, (barcode, barcode, session.get('user_id')))
        barang = cursor.fetchone()
        cursor.close()
        connection.close()
        
        if barang:
            cart = session.get('cart', [])
            existing_item = next((item for item in cart if str(item['id']) == str(barang['id'])), None)
            stok = int(barang.get('stok') or 0)
            if stok <= 0:
                return jsonify({
                    'success': False,
                    'message': f"Stok {barang['nama_barang']} habis. Segera isi kembali sebelum menambahkan ke keranjang."
                }), 409
            requested_quantity = (int(existing_item['jumlah']) if existing_item else 0) + 1
            if requested_quantity > stok:
                return jsonify({
                    'success': False,
                    'message': f"Stok {barang['nama_barang']} tidak mencukupi. Stok tersedia: {stok}."
                }), 409
            if existing_item:
                existing_item['jumlah'] = requested_quantity
                existing_item['subtotal'] = requested_quantity * existing_item['harga_jual']
                existing_item['stok'] = stok
            else:
                cart.append({
                    'id': barang['id'],
                    'kode_barang': barang['kode_barang'],
                    'nama_barang': barang['nama_barang'],
                    'harga_jual': float(barang['harga_jual']),
                    'jumlah': 1,
                    'subtotal': float(barang['harga_jual']),
                    'stok': stok
                })
            session['cart'] = cart
            session.modified = True
            return jsonify({'success': True, 'barang': barang, 'cart': cart})
        else:
            return jsonify({'success': False, 'message': 'Barang tidak ditemukan!'})
    
    return jsonify({'success': False, 'message': 'Gagal terhubung ke database!'})

@main_bp.route('/laporan', methods=['GET', 'POST'])
@login_required
def laporan():
    report_user_id = _transaction_view_user_id()
    jenis_laporan = request.values.get('jenis', 'harian')
    tanggal = request.values.get('tanggal', datetime.now().strftime('%Y-%m-%d'))
    
    if request.method == 'POST':
        if 'export_pdf' in request.form:
            return export_to_pdf(jenis_laporan, tanggal, user_id=report_user_id)
        elif 'export_excel' in request.form:
            return export_to_excel(jenis_laporan, tanggal, user_id=report_user_id)
    
    data = get_laporan_data(jenis_laporan, tanggal, user_id=report_user_id)
    return render_template('laporan.html', data=data, jenis=jenis_laporan, tanggal=tanggal)

@main_bp.route('/pengguna', methods=['GET', 'POST'])
@login_required
@admin_required
def pengguna():
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'add':
            username = request.form.get('username')
            password = request.form.get('password')
            nama_lengkap = request.form.get('nama_lengkap')
            role = request.form.get('role')
            
            result = add_user(username, password, nama_lengkap, role, owner_id=session.get('user_id'))
            if result:
                # Newly created admin accounts must be activated by the owner/admin
                try:
                    conn = get_db_connection()
                    if conn:
                        cur = conn.cursor()
                        # ensure new account is inactive until owner activates
                        cur.execute("UPDATE users SET is_active=0, active_from=NULL, active_until=NULL, duration_days=NULL WHERE username=%s", (username,))
                        conn.commit()
                        cur.close()
                        conn.close()
                except Exception:
                    pass
                flash('Pengguna berhasil ditambahkan! (Akun dalam keadaan non-aktif, perlu aktivasi oleh pemilik.)', 'success')
            else:
                flash('Gagal menambahkan pengguna!', 'danger')
        
        elif action == 'edit':
            user_id = request.form.get('user_id')
            username = request.form.get('username')
            password = request.form.get('password')
            nama_lengkap = request.form.get('nama_lengkap')
            role = request.form.get('role')
            
            result = update_user(user_id, username, password, nama_lengkap, role, owner_id=session.get('user_id'))
            if result:
                flash('Pengguna berhasil diperbarui!', 'success')
            else:
                flash('Gagal memperbarui pengguna!', 'danger')
        
        elif action == 'delete':
            user_id = request.form.get('user_id')
            result = delete_user(user_id, owner_id=session.get('user_id'))
            if result:
                flash('Pengguna berhasil dihapus!', 'success')
            else:
                flash('Gagal menghapus pengguna!', 'danger')
        
        return redirect(url_for('main.pengguna'))
    
    user_list = get_all_users(owner_id=session.get('user_id'))
    return render_template('pengguna.html', user_list=user_list)

@main_bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    current_user_id = session.get('user_id')
    user = get_user_by_id(current_user_id)
    if not user:
        flash('Pengguna tidak ditemukan.', 'danger')
        return redirect(url_for('main.dashboard'))

    if request.method == 'POST':
        if session.get('role') not in ('admin', 'kasir'):
            abort(403)
        if 'profile_photo' in request.files and request.files['profile_photo'].filename:
            file = request.files['profile_photo']
            filename = secure_filename(file.filename)
            upload_folder = os.path.join('static', 'uploads')
            os.makedirs(upload_folder, exist_ok=True)
            filename = f'user_{current_user_id}_{filename}'
            file.save(os.path.join(upload_folder, filename))

            try:
                connection = get_db_connection()
                if connection:
                    cursor = connection.cursor()
                    cursor.execute("UPDATE users SET profile_photo = %s WHERE id = %s", (filename, current_user_id))
                    connection.commit()
                    cursor.close()
                    connection.close()
                    session['profile_photo'] = filename
                    flash('Foto profil berhasil diperbarui.', 'success')
            except Error as e:
                print(f"Error updating profile photo: {e}")
                flash('Gagal menyimpan foto profil.', 'danger')
        else:
            flash('Pilih foto profil terlebih dahulu.', 'warning')

        return redirect(url_for('main.profile'))

    return render_template('profile.html', user=user)


@main_bp.route('/settings', methods=['GET', 'POST'])
@login_required
@admin_required
def settings():
    owner_id = get_account_owner_id(session.get('user_id'))
    settings_data = get_store_settings(owner_id)
    connection = get_db_connection()
    if not connection:
        if request.method == 'POST':
            flash('Gagal terhubung ke database. Pengaturan belum disimpan.', 'danger')
        return render_template('settings.html', settings=settings_data)

    if request.method == 'POST':
        nama_toko = request.form.get('nama_toko', '').strip()
        alamat = request.form.get('alamat', '').strip()
        telepon = request.form.get('telepon', '').strip()
        email = request.form.get('email', '').strip()
        notification_email = request.form.get('notification_email', '').strip()
        footer_message = request.form.get('footer_message', '').strip()
        email_notification = 1 if request.form.get('email_notification') else 0

        try:
            low_stock_threshold = int(request.form.get('low_stock_threshold', '10'))
            if low_stock_threshold < 0:
                raise ValueError
        except (TypeError, ValueError):
            connection.close()
            flash('Batas stok rendah harus berupa bilangan bulat nol atau lebih.', 'danger')
            return render_template('settings.html', settings=settings_data)

        if not nama_toko:
            connection.close()
            flash('Nama toko wajib diisi.', 'danger')
            return render_template('settings.html', settings=settings_data)

        if notification_email and (
            '@' not in notification_email
            or any(character.isspace() for character in notification_email)
            or '.' not in notification_email.rsplit('@', 1)[-1]
        ):
            connection.close()
            flash('Alamat email notifikasi tidak valid.', 'danger')
            return render_template('settings.html', settings=settings_data)

        logo_filename = settings_data.get('logo')
        uploaded_file = request.files.get('logo')
        if uploaded_file and uploaded_file.filename:
            safe_name = secure_filename(uploaded_file.filename)
            extension = os.path.splitext(safe_name)[1].lower()
            if extension not in {'.png', '.jpg', '.jpeg', '.gif', '.webp'}:
                connection.close()
                flash('Format logo harus PNG, JPG, JPEG, GIF, atau WEBP.', 'danger')
                return render_template('settings.html', settings=settings_data)
            logo_filename = f'store_{owner_id}_{uuid.uuid4().hex}{extension}'
            upload_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'static', 'uploads')
            os.makedirs(upload_path, exist_ok=True)
            uploaded_file.save(os.path.join(upload_path, logo_filename))

        cursor = connection.cursor()
        cursor.execute("""
            INSERT INTO settings (
                owner_id, nama_toko, alamat, telepon, email, notification_email, logo,
                footer_message, low_stock_threshold, email_notification
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                nama_toko = VALUES(nama_toko),
                alamat = VALUES(alamat),
                telepon = VALUES(telepon),
                email = VALUES(email),
                notification_email = VALUES(notification_email),
                logo = VALUES(logo),
                footer_message = VALUES(footer_message),
                low_stock_threshold = VALUES(low_stock_threshold),
                email_notification = VALUES(email_notification)
        """, (
            owner_id, nama_toko, alamat, telepon, email, notification_email or None,
            logo_filename, footer_message, low_stock_threshold, email_notification
        ))
        connection.commit()
        cursor.close()
        connection.close()
        flash('Pengaturan berhasil disimpan!', 'success')
        return redirect(url_for('main.settings'))
    
    return render_template('settings.html', settings=settings_data)

@main_bp.route('/riwayat-transaksi')
@login_required
def riwayat_transaksi():
    limit = request.args.get('limit', 50)
    transactions = get_transactions(limit, user_id=_transaction_view_user_id())
    return render_template('riwayat_transaksi.html', transactions=transactions)

@main_bp.route('/stok-barang')
@login_required
def stok_barang():
    owner_id = get_account_owner_id(session.get('user_id'))
    store_settings = get_store_settings(owner_id)
    low_stock_threshold = int(store_settings.get('low_stock_threshold', 10))
    connection = get_db_connection()
    barang_list = []
    low_stock = []
    stok_grafik = []
    total_stok = 0
    
    if connection:
        cursor = connection.cursor(dictionary=True)
        cursor.execute("""
            SELECT b.*, k.nama_kategori 
            FROM barang b 
            LEFT JOIN kategori k ON b.kategori_id = k.id 
            WHERE b.user_id = %s
            ORDER BY b.stok ASC
        """, (owner_id,))
        barang_list = cursor.fetchall()
        
        # Get low stock items
        low_stock = [b for b in barang_list if b['stok'] <= low_stock_threshold]
        total_stok = sum(int(barang.get('stok') or 0) for barang in barang_list)
        stok_maksimum = max((int(barang.get('stok') or 0) for barang in barang_list), default=0) or 1
        stok_grafik = sorted(
            [
                {
                    'nama_barang': barang['nama_barang'],
                    'kode_barang': barang['kode_barang'],
                    'stok': int(barang.get('stok') or 0),
                    'persentase': max(0, int(barang.get('stok') or 0)) / stok_maksimum * 100,
                }
                for barang in barang_list
            ],
            key=lambda barang: barang['stok'],
            reverse=True,
        )
        
        cursor.close()
        connection.close()
    
    return render_template(
        'stok_barang.html', barang_list=barang_list, low_stock=low_stock,
        stok_grafik=stok_grafik, total_stok=total_stok,
        low_stock_threshold=low_stock_threshold
    )

@main_bp.route('/barang-terlaris')
@login_required
def barang_terlaris():
    report_user_id = _transaction_view_user_id()
    connection = get_db_connection()
    terlaris = []
    
    if connection:
        cursor = connection.cursor(dictionary=True)
        cursor.execute("""
            SELECT b.nama_barang, b.kode_barang, SUM(dt.jumlah) as total_terjual, 
                   SUM(dt.subtotal) as total_pendapatan
            FROM detail_transaksi dt
            JOIN barang b ON dt.barang_id = b.id
            JOIN transaksi t ON dt.transaksi_id = t.id
                        WHERE t.status = 'selesai'
                            AND t.user_id IN (SELECT id FROM users WHERE id = %s OR owner_id = %s)
            GROUP BY b.id
            ORDER BY total_terjual DESC
            LIMIT 10
        """, (report_user_id, report_user_id))
        terlaris = cursor.fetchall()
        cursor.close()
        connection.close()
    
    return render_template('barang_terlaris.html', terlaris=terlaris)

@main_bp.route('/hapus-transaksi', methods=['POST'])
@login_required
@admin_required
def hapus_transaksi():
    kode_transaksi = request.form.get('kode_transaksi')
    
    if kode_transaksi:
        connection = get_db_connection()
        if connection:
            cursor = connection.cursor()
            # Hapus detail transaksi dulu
            cursor.execute("""
                DELETE dt FROM detail_transaksi dt
                JOIN transaksi t ON dt.transaksi_id = t.id
                WHERE t.kode_transaksi = %s
            """, (kode_transaksi,))
            # Hapus transaksi
            cursor.execute("DELETE FROM transaksi WHERE kode_transaksi = %s", (kode_transaksi,))
            connection.commit()
            cursor.close()
            connection.close()
            flash('Transaksi berhasil dihapus!', 'success')
        else:
            flash('Gagal terhubung ke database!', 'danger')
    else:
        flash('Kode transaksi tidak ditemukan!', 'danger')
    
    return redirect(url_for('main.riwayat_transaksi'))
