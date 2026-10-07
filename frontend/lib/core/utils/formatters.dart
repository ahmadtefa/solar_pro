import 'package:intl/intl.dart';

/// Locale-aware formatting for money, numbers, dates and statuses.
class Fmt {
  const Fmt._();

  static String number(Object? value, {String locale = 'en', int? decimals}) {
    final num? parsed = toNum(value);
    if (parsed == null) return value?.toString() ?? '';
    final NumberFormat format = decimals == null
        ? NumberFormat.decimalPattern(locale)
        : NumberFormat.decimalPatternDigits(locale: locale, decimalDigits: decimals);
    return format.format(parsed);
  }

  static String money(Object? value, {String locale = 'en', String? currency, int decimals = 2}) {
    final num? parsed = toNum(value);
    if (parsed == null) return value?.toString() ?? '';
    final String formatted = NumberFormat.decimalPatternDigits(locale: locale, decimalDigits: decimals).format(parsed);
    return currency == null || currency.isEmpty ? formatted : '$formatted $currency';
  }

  static String quantity(Object? value, {String locale = 'en'}) => number(value, locale: locale, decimals: 0);

  static String percent(Object? value, {String locale = 'en'}) {
    final num? parsed = toNum(value);
    if (parsed == null) return '';
    return '${NumberFormat.decimalPatternDigits(locale: locale, decimalDigits: 2).format(parsed)}%';
  }

  static String date(Object? value, {String locale = 'en'}) {
    final DateTime? parsed = toDate(value);
    if (parsed == null) return value?.toString() ?? '';
    return DateFormat.yMd(locale).format(parsed);
  }

  static String dateTime(Object? value, {String locale = 'en'}) {
    final DateTime? parsed = toDate(value);
    if (parsed == null) return value?.toString() ?? '';
    return DateFormat.yMd(locale).add_Hm().format(parsed);
  }

  static String isoDate(Object? value) {
    final DateTime? parsed = toDate(value);
    if (parsed == null) return value?.toString() ?? '';
    return DateFormat('yyyy-MM-dd').format(parsed);
  }

  static String relative(Object? value, {String locale = 'en'}) {
    final DateTime? parsed = toDate(value);
    if (parsed == null) return '';
    final Duration difference = DateTime.now().difference(parsed);
    if (difference.inMinutes < 1) return locale == 'ar' ? 'الآن' : 'just now';
    if (difference.inHours < 1) {
      return locale == 'ar' ? 'قبل ${difference.inMinutes} دقيقة' : '${difference.inMinutes} min ago';
    }
    if (difference.inDays < 1) {
      return locale == 'ar' ? 'قبل ${difference.inHours} ساعة' : '${difference.inHours} h ago';
    }
    if (difference.inDays < 30) {
      return locale == 'ar' ? 'قبل ${difference.inDays} يوم' : '${difference.inDays} d ago';
    }
    return date(value, locale: locale);
  }

  static num? toNum(Object? value) {
    if (value == null) return null;
    if (value is num) return value;
    final String text = '$value'.trim();
    if (text.isEmpty) return null;
    return num.tryParse(text);
  }

  static DateTime? toDate(Object? value) {
    if (value == null) return null;
    if (value is DateTime) return value;
    return DateTime.tryParse('$value');
  }

  static bool toBool(Object? value) {
    if (value is bool) return value;
    if (value is num) return value != 0;
    final String text = '$value'.toLowerCase();
    return text == 'true' || text == '1' || text == 'yes';
  }

  /// Human readable status key inside the `status.*` namespace.
  static String statusKey(Object? status) {
    final String value = '${status ?? ''}'.trim().toLowerCase().replaceAll('-', '_').replaceAll(' ', '_');
    return value.isEmpty ? 'common.none' : 'status.$value';
  }
}

/// Inclusive date range used by report and list filters.
class DateRange {
  const DateRange(this.from, this.to);

  final DateTime from;
  final DateTime to;

  static DateRange today() {
    final DateTime now = DateTime.now();
    final DateTime day = DateTime(now.year, now.month, now.day);
    return DateRange(day, day);
  }

  static DateRange thisWeek() {
    final DateTime now = DateTime.now();
    final DateTime start = DateTime(now.year, now.month, now.day).subtract(Duration(days: now.weekday - 1));
    return DateRange(start, start.add(const Duration(days: 6)));
  }

  static DateRange thisMonth() {
    final DateTime now = DateTime.now();
    return DateRange(DateTime(now.year, now.month, 1), DateTime(now.year, now.month + 1, 0));
  }

  static DateRange thisQuarter() {
    final DateTime now = DateTime.now();
    final int quarterStartMonth = ((now.month - 1) ~/ 3) * 3 + 1;
    return DateRange(DateTime(now.year, quarterStartMonth, 1), DateTime(now.year, quarterStartMonth + 3, 0));
  }

  static DateRange thisYear() {
    final DateTime now = DateTime.now();
    return DateRange(DateTime(now.year, 1, 1), DateTime(now.year, 12, 31));
  }

  String get fromIso => DateFormat('yyyy-MM-dd').format(from);
  String get toIso => DateFormat('yyyy-MM-dd').format(to);
}
