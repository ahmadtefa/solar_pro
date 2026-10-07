import 'package:flutter_test/flutter_test.dart';
import 'package:kayan_erp/core/utils/formatters.dart';

void main() {
  group('formatters', () {
    test('money and numbers parse strings coming from the API', () {
      expect(Fmt.toNum('1234.5000'), closeTo(1234.5, 0.0001));
      expect(Fmt.money('1000.2500', currency: 'EGP'), contains('1,000.25'));
      expect(Fmt.money('1000.25', locale: 'ar'), isNotEmpty);
    });

    test('invalid numbers are returned untouched instead of throwing', () {
      expect(Fmt.money(null), '');
      expect(Fmt.money('not-a-number'), 'not-a-number');
    });

    test('dates normalise to ISO for API filters', () {
      expect(Fmt.isoDate('2026-02-03T10:11:12'), '2026-02-03');
      expect(Fmt.isoDate(DateTime(2026, 12, 31)), '2026-12-31');
      expect(Fmt.isoDate('nonsense'), 'nonsense');
    });

    test('status keys map to the localisation namespace', () {
      expect(Fmt.statusKey('PARTIALLY FULFILLED'), 'status.partially_fulfilled');
      expect(Fmt.statusKey(null), 'common.none');
    });

    test('date ranges cover the current period inclusively', () {
      final DateRange month = DateRange.thisMonth();
      expect(month.from.day, 1);
      expect(month.to.day, greaterThanOrEqualTo(28));
      expect(month.fromIso.compareTo(month.toIso), lessThan(0));
    });
  });
}
