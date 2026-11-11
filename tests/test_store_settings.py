import unittest
from unittest.mock import Mock, patch

from flask import Flask, session

from app.routes import main_bp, settings as settings_route
from app.utils import get_store_settings


class StoreSettingsTest(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.secret_key = 'test-secret'
        self.app.register_blueprint(main_bp)

    @patch('app.utils.get_db_connection')
    def test_settings_lookup_is_scoped_to_store_owner(self, get_db_connection):
        cursor = Mock()
        cursor.fetchone.return_value = {
            'owner_id': 12,
            'nama_toko': 'Toko Ilham',
            'low_stock_threshold': 4,
            'notification_email': 'ilham@example.com',
            'email_notification': 1,
        }
        connection = Mock()
        connection.cursor.return_value = cursor
        get_db_connection.return_value = connection

        result = get_store_settings(12)

        self.assertEqual(result['nama_toko'], 'Toko Ilham')
        self.assertEqual(result['low_stock_threshold'], 4)
        cursor.execute.assert_called_once_with(
            'SELECT * FROM settings WHERE owner_id = %s LIMIT 1',
            (12,)
        )
        connection.close.assert_called_once()

    @patch('app.routes.get_store_settings', return_value={'logo': None})
    @patch('app.routes.get_account_owner_id', return_value=12)
    @patch('app.routes.get_db_connection')
    @patch('app.routes._admin_access_is_valid', return_value=True)
    def test_settings_save_targets_only_current_owner(
        self, _access_valid, get_db_connection, _get_owner_id, _get_store_settings
    ):
        cursor = Mock()
        connection = Mock()
        connection.cursor.return_value = cursor
        get_db_connection.return_value = connection

        with self.app.test_request_context(
            '/settings',
            method='POST',
            data={
                'nama_toko': 'Toko Ilham',
                'alamat': 'Bandung',
                'telepon': '08123456789',
                'email': 'toko@example.com',
                'notification_email': 'alerts@example.com',
                'footer_message': 'Terima kasih',
                'low_stock_threshold': '4',
                'email_notification': '1',
            },
        ):
            session['user_id'] = 7
            session['role'] = 'admin'
            response = settings_route()

        self.assertEqual(response.status_code, 302)
        sql, parameters = cursor.execute.call_args.args
        self.assertIn('ON DUPLICATE KEY UPDATE', sql)
        self.assertEqual(parameters[0], 12)
        self.assertEqual(parameters[5], 'alerts@example.com')
        self.assertEqual(parameters[9], 1)
        connection.commit.assert_called_once()
        connection.close.assert_called_once()


if __name__ == '__main__':
    unittest.main()
