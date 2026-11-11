import unittest
from decimal import Decimal
from unittest.mock import Mock, patch

from flask import Flask, session

from app.routes import scan_barcode, transaksi


class ScannerRouteTest(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.secret_key = 'test-secret'

    def _call_scan_barcode(self, cart=None):
        with self.app.test_request_context(
            '/scan-barcode',
            method='POST',
            json={'barcode': '1234567890123'}
        ):
            session['user_id'] = 5
            if cart is not None:
                session['cart'] = cart
            response = scan_barcode()
            if isinstance(response, tuple):
                response = response[0]
            return response.get_json()

    @patch('app.routes.get_db_connection')
    def test_scan_adds_product_to_cart(self, get_db_connection):
        product = {
            'id': 7,
            'kode_barang': 'SKU-7',
            'nama_barang': 'Produk',
            'harga_jual': Decimal('25.50'),
            'stok': 10
        }
        cursor = Mock()
        cursor.fetchone.return_value = product
        connection = Mock()
        connection.cursor.return_value = cursor
        get_db_connection.return_value = connection

        result = self._call_scan_barcode()

        self.assertTrue(result['success'])
        self.assertEqual(result['cart'], [{
            'id': 7,
            'kode_barang': 'SKU-7',
            'nama_barang': 'Produk',
            'harga_jual': 25.5,
            'jumlah': 1,
            'subtotal': 25.5,
            'stok': 10
        }])
        self.assertEqual(
            cursor.execute.call_args.args[1],
            ('1234567890123', '1234567890123', 5)
        )
        query = ' '.join(cursor.execute.call_args.args[0].split())
        self.assertIn('FROM users u', query)
        self.assertIn("WHEN u.role = 'admin' THEN u.id", query)
        self.assertIn('b.user_id = (', query)
        connection.close.assert_called_once()

    @patch('app.routes.get_db_connection')
    def test_scan_increments_matching_cart_item(self, get_db_connection):
        product = {
            'id': 7,
            'kode_barang': 'SKU-7',
            'nama_barang': 'Produk',
            'harga_jual': Decimal('25.50'),
            'stok': 10
        }
        cursor = Mock()
        cursor.fetchone.return_value = product
        connection = Mock()
        connection.cursor.return_value = cursor
        get_db_connection.return_value = connection

        result = self._call_scan_barcode([{
            'id': '7',
            'kode_barang': 'SKU-7',
            'nama_barang': 'Produk',
            'harga_jual': 25.5,
            'jumlah': 2,
            'subtotal': 51.0,
            'stok': 10
        }])

        self.assertTrue(result['success'])
        self.assertEqual(result['cart'][0]['jumlah'], 3)
        self.assertEqual(result['cart'][0]['subtotal'], 76.5)

    @patch('app.routes.get_db_connection')
    def test_scan_rejects_product_with_zero_stock(self, get_db_connection):
        cursor = Mock()
        cursor.fetchone.return_value = {
            'id': 7,
            'kode_barang': 'SKU-7',
            'nama_barang': 'Produk',
            'harga_jual': Decimal('25.50'),
            'stok': 0
        }
        connection = Mock()
        connection.cursor.return_value = cursor
        get_db_connection.return_value = connection

        result = self._call_scan_barcode()

        self.assertFalse(result['success'])
        self.assertIn('Stok Produk habis', result['message'])

    @patch('app.routes.get_db_connection')
    def test_scan_cannot_add_more_than_available_stock(self, get_db_connection):
        cursor = Mock()
        cursor.fetchone.return_value = {
            'id': 7,
            'kode_barang': 'SKU-7',
            'nama_barang': 'Produk',
            'harga_jual': Decimal('25.50'),
            'stok': 1
        }
        connection = Mock()
        connection.cursor.return_value = cursor
        get_db_connection.return_value = connection
        current_cart = [{
            'id': 7,
            'kode_barang': 'SKU-7',
            'nama_barang': 'Produk',
            'harga_jual': 25.5,
            'jumlah': 1,
            'subtotal': 25.5,
            'stok': 1
        }]

        result = self._call_scan_barcode(current_cart)

        self.assertFalse(result['success'])
        self.assertIn('Stok Produk tidak mencukupi', result['message'])

    @patch('app.routes.get_barang_by_id')
    @patch('app.routes.get_account_owner_id', return_value=2)
    def test_transaction_rejects_product_with_zero_stock(self, _get_owner_id, get_barang_by_id):
        get_barang_by_id.return_value = {
            'id': 7,
            'kode_barang': 'SKU-7',
            'nama_barang': 'Produk',
            'harga_jual': Decimal('25.50'),
            'stok': 0
        }

        with self.app.test_request_context(
            '/transaksi',
            method='POST',
            json={'barang_id': 7, 'jumlah': 1}
        ):
            session['user_id'] = 5
            response = transaksi()
            response, response_status = response if isinstance(response, tuple) else (response, 200)
            result = response.get_json()
            self.assertFalse(result['success'])
            self.assertEqual(response_status, 409)
            self.assertIn('Stok Produk habis', result['message'])
            self.assertNotIn('cart', session)

    @patch('app.routes.get_all_barang')
    @patch('app.routes.get_account_owner_id', return_value=2)
    def test_ajax_transaction_does_not_load_entire_catalog(self, _get_owner_id, get_all_barang):
        with self.app.test_request_context('/transaksi', method='POST', json={}):
            session['user_id'] = 5
            result = transaksi().get_json()

        self.assertFalse(result['success'])
        get_all_barang.assert_not_called()


if __name__ == '__main__':
    unittest.main()
