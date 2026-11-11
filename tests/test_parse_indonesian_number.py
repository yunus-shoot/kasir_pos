import unittest

from app.utils import parse_indonesian_number


class ParseIndonesianNumberTest(unittest.TestCase):
    def test_standard_decimal(self):
        self.assertEqual(parse_indonesian_number('1000.50'), 1000.5)

    def test_indonesian_grouped_format(self):
        self.assertEqual(parse_indonesian_number('1.234,50'), 1234.5)

    def test_currency_prefix(self):
        self.assertEqual(parse_indonesian_number('Rp 1.234,50'), 1234.5)

    def test_thousands_separator_single_dot(self):
        self.assertEqual(parse_indonesian_number('5.500'), 5500.0)

    def test_blank_value_raises(self):
        with self.assertRaises(ValueError):
            parse_indonesian_number('')


if __name__ == '__main__':
    unittest.main()
