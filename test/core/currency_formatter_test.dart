import 'package:flutter_test/flutter_test.dart';
import 'package:solar_pro/core/utils/currency_formatter.dart';

void main() {
  group('CurrencyFormatter.number', () {
    test('groups thousands', () {
      expect(CurrencyFormatter.number(0), '0.00');
      expect(CurrencyFormatter.number(999), '999.00');
      expect(CurrencyFormatter.number(1000), '1,000.00');
      expect(CurrencyFormatter.number(1234567.5), '1,234,567.50');
      expect(CurrencyFormatter.number(1000000), '1,000,000.00');
    });

    test('honours the decimals argument', () {
      expect(CurrencyFormatter.number(1200, decimals: 0), '1,200');
      expect(CurrencyFormatter.number(1200.456, decimals: 0), '1,200');
      expect(CurrencyFormatter.number(1200.456, decimals: 3), '1,200.456');
    });

    test('keeps the minus sign outside the grouping', () {
      expect(CurrencyFormatter.number(-1234.5), '-1,234.50');
      expect(CurrencyFormatter.number(-999), '-999.00');
    });
  });

  group('CurrencyFormatter.money', () {
    test('appends the Egyptian pound suffix', () {
      expect(CurrencyFormatter.money(1500), '1,500.00 ج.م');
      expect(CurrencyFormatter.money(0), '0.00 ج.م');
      expect(CurrencyFormatter.money(1500, decimals: 0), '1,500 ج.م');
    });
  });
}
