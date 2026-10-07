/// Small, `intl`-free helpers for printing money the way the Arabic UI does it.
///
/// Implemented by hand (instead of `NumberFormat`) so it works in unit tests
/// without initialising any locale data.
class CurrencyFormatter {
  CurrencyFormatter._();

  /// Currency suffix used across the app (Egyptian pound).
  static const String currency = 'ج.م';

  /// Formats [value] as a plain number with thousands separators.
  ///
  /// ```dart
  /// CurrencyFormatter.number(1234567.5); // '1,234,567.50'
  /// CurrencyFormatter.number(1200, decimals: 0); // '1,200'
  /// ```
  static String number(double value, {int decimals = 2}) {
    final fixed = value.toStringAsFixed(decimals);
    final parts = fixed.split('.');
    final integerPart = parts.first;
    var grouped = integerPart;
    if (grouped.startsWith('-')) {
      grouped = '-${_groupDigits(grouped.substring(1))}';
    } else {
      grouped = _groupDigits(grouped);
    }
    if (parts.length == 1) return grouped;
    final fraction = parts[1];
    if (decimals == 0) return grouped;
    return '$grouped.$fraction';
  }

  /// Formats [value] as money: `1,234.00 ج.م`.
  static String money(double value, {int decimals = 2}) {
    return '${number(value, decimals: decimals)} $currency';
  }

  static String _groupDigits(String digits) {
    if (digits.length <= 3) return digits;
    final buffer = StringBuffer();
    var count = 0;
    for (var i = digits.length - 1; i >= 0; i--) {
      buffer.write(digits[i]);
      count++;
      if (count % 3 == 0 && i > 0) {
        buffer.write(',');
      }
    }
    return buffer.toString().split('').reversed.join();
  }
}
