import unittest
from decimal import Decimal
from unittest.mock import Mock, patch

from flask import Flask, session

from app.accounting import account_totals, validate_journal_lines
from app.routes import _statement_balance, main_bp


class UmkmAccountingTest(unittest.TestCase):
    def test_journal_lines_must_balance(self):
        lines = validate_journal_lines([
            {'account_id': 1, 'debit': '125000', 'credit': '0'},
            {'account_id': 2, 'debit': '0', 'credit': '125000'},
        ])
        self.assertEqual(lines[0]['debit'], Decimal('125000.00'))
        self.assertEqual(lines[1]['credit'], Decimal('125000.00'))

    def test_journal_lines_reject_unbalanced_amounts(self):
        with self.assertRaisesRegex(ValueError, 'harus sama'):
            validate_journal_lines([
                {'account_id': 1, 'debit': '100', 'credit': '0'},
                {'account_id': 2, 'debit': '0', 'credit': '90'},
            ])

    def test_journal_lines_explain_how_to_fix_both_sides_in_one_row(self):
        with self.assertRaisesRegex(ValueError, 'Kosongkan salah satunya'):
            validate_journal_lines([
                {'account_id': 1, 'debit': '100', 'credit': '100'},
            ])

    def test_journal_lines_require_two_nonzero_rows(self):
        with self.assertRaisesRegex(ValueError, 'minimal dua baris'):
            validate_journal_lines([
                {'account_id': 1, 'debit': '100', 'credit': '0'},
            ])

    def test_journal_lines_reject_non_finite_numbers(self):
        with self.assertRaisesRegex(ValueError, 'angka yang valid'):
            validate_journal_lines([
                {'account_id': 1, 'debit': 'NaN', 'credit': '0'},
                {'account_id': 2, 'debit': '0', 'credit': 'NaN'},
            ])

    def test_account_totals_use_normal_balance(self):
        totals = account_totals([
            {
                'account_id': 1, 'account_code': '11001', 'account_name': 'Kas',
                'account_type': 'aset', 'normal_balance': 'debit',
                'debit': Decimal('150'), 'credit': Decimal('40'),
            },
            {
                'account_id': 2, 'account_code': '41001', 'account_name': 'Penjualan',
                'account_type': 'pendapatan', 'normal_balance': 'kredit',
                'debit': Decimal('20'), 'credit': Decimal('200'),
            },
        ])
        self.assertEqual([item['balance'] for item in totals], [Decimal('110'), Decimal('180')])

    def test_financial_statement_signs_contra_accounts_correctly(self):
        contra_asset = {
            'account_type': 'aset', 'debit': Decimal('0'), 'credit': Decimal('25')
        }
        sales_return = {
            'account_type': 'pendapatan', 'debit': Decimal('25'), 'credit': Decimal('0')
        }
        owner_withdrawal = {
            'account_type': 'ekuitas', 'debit': Decimal('25'), 'credit': Decimal('0')
        }
        self.assertEqual(_statement_balance(contra_asset), Decimal('-25'))
        self.assertEqual(_statement_balance(sales_return), Decimal('-25'))
        self.assertEqual(_statement_balance(owner_withdrawal), Decimal('-25'))

    def test_umkm_role_cannot_open_cashier_routes(self):
        app = Flask(__name__, template_folder='../templates')
        app.secret_key = 'test-secret'
        app.register_blueprint(main_bp)
        with app.test_client() as client:
            with client.session_transaction() as browser_session:
                browser_session['user_id'] = 7
                browser_session['role'] = 'umkm'
            response = client.get('/transaksi')
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.location.endswith('/umkm/'))

    def test_non_umkm_role_cannot_open_accounting_layer(self):
        app = Flask(__name__)
        app.secret_key = 'test-secret'
        app.register_blueprint(main_bp)
        with app.test_client() as client:
            with client.session_transaction() as browser_session:
                browser_session['user_id'] = 7
                browser_session['role'] = 'kasir'
            response = client.get('/umkm/akun')
        self.assertEqual(response.status_code, 302)

    @patch('app.routes.get_db_connection')
    def test_umkm_profile_uses_pos_shell_without_cashier_menu(self, get_db_connection):
        cursor = Mock()
        cursor.fetchone.return_value = {
            'username': 'umkm',
            'nama_lengkap': 'Pembukuan UMKM',
            'role': 'umkm',
            'created_at': None,
        }
        connection = Mock()
        connection.cursor.return_value = cursor
        get_db_connection.return_value = connection

        app = Flask(__name__, template_folder='../templates')
        app.secret_key = 'test-secret'
        app.register_blueprint(main_bp)
        with app.test_client() as client:
            with client.session_transaction() as browser_session:
                browser_session['user_id'] = 7
                browser_session['role'] = 'umkm'
                browser_session['nama_lengkap'] = 'Pembukuan UMKM'
            response = client.get('/umkm/akun-saya')

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Akun Saya', response.data)
        self.assertIn(b'Logout', response.data)
        self.assertNotIn(b'Transaksi Baru', response.data)
        self.assertNotIn(b'/transaksi', response.data)
        connection.close.assert_called_once()

    @patch('app.routes.get_journal_lines', return_value=[])
    @patch('app.routes.get_accounts')
    def test_invalid_journal_keeps_form_values_and_explains_the_row(
        self, get_accounts, _get_journal_lines
    ):
        get_accounts.return_value = [{
            'id': 1,
            'account_code': '11001',
            'account_name': 'Kas',
            'account_type': 'aset',
            'normal_balance': 'debit',
        }]
        app = Flask(__name__, template_folder='../templates')
        app.secret_key = 'test-secret'
        app.add_template_filter(lambda value: str(value or 0), 'id_number')
        app.register_blueprint(main_bp)
        with app.test_client() as client:
            with client.session_transaction() as browser_session:
                browser_session['user_id'] = 7
                browser_session['role'] = 'umkm'
            response = client.post('/umkm/jurnal', data={
                'journal_date': '2026-11-10',
                'reference': 'TEST-1',
                'description': 'Uji validasi jurnal',
                'journal_type': 'umum',
                'cash_flow_category': 'operasional',
                'account_id': ['1', '', ''],
                'debit': ['100000', '', ''],
                'credit': ['100000', '', ''],
            })

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Kosongkan salah satunya', response.data)
        self.assertIn(b'value="100000"', response.data)
        self.assertIn(b'Uji validasi jurnal', response.data)


if __name__ == '__main__':
    unittest.main()
