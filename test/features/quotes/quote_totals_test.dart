import 'package:flutter_test/flutter_test.dart';
import 'package:solar_pro/features/quotes/data/models/quote_item.dart';
import 'package:solar_pro/features/quotes/domain/quote_totals.dart';

QuoteItem _item({
  required int quantity,
  required double unitPrice,
  String description = 'صنف',
  String unit = 'وحدة',
}) {
  return QuoteItem.create(
    quoteId: 1,
    description: description,
    quantity: quantity,
    unitPrice: unitPrice,
    unit: unit,
  );
}

void main() {
  group('QuoteTotals.compute', () {
    test('sums quantity x unit price', () {
      final totals = QuoteTotals.compute(items: <QuoteItem>[
        _item(quantity: 10, unitPrice: 100),
        _item(quantity: 5, unitPrice: 200),
      ]);

      expect(totals.subtotal, 2000);
      expect(totals.discountAmount, 0);
      expect(totals.taxAmount, 0);
      expect(totals.total, 2000);
    });

    test('applies the discount before the tax', () {
      final totals = QuoteTotals.compute(
        items: <QuoteItem>[_item(quantity: 10, unitPrice: 100)],
        discountPercent: 10,
        taxPercent: 5,
      );

      expect(totals.subtotal, 1000);
      expect(totals.discountAmount, 100);
      expect(totals.taxAmount, closeTo(45, 1e-9)); // 5% of 900
      expect(totals.total, closeTo(945, 1e-9));
    });

    test('an empty quote costs nothing', () {
      final totals = QuoteTotals.compute(items: <QuoteItem>[]);
      expect(totals.subtotal, 0);
      expect(totals.total, 0);
    });

    test('clamps percentages to 0..100', () {
      final totals = QuoteTotals.compute(
        items: <QuoteItem>[_item(quantity: 1, unitPrice: 1000)],
        discountPercent: 150,
        taxPercent: -20,
      );

      expect(totals.discountPercent, 100);
      expect(totals.taxPercent, 0);
      expect(totals.subtotal, 1000);
      expect(totals.total, 0);
    });

    test('equality and toString are stable', () {
      final a = QuoteTotals.compute(
          items: <QuoteItem>[_item(quantity: 1, unitPrice: 100)]);
      final b = QuoteTotals.compute(
          items: <QuoteItem>[_item(quantity: 1, unitPrice: 100)]);
      expect(a, equals(b));
      expect(a.hashCode, b.hashCode);
      expect(a.toString(), contains('100'));
    });
  });

  group('QuoteItem', () {
    test('lineTotal is quantity x unitPrice', () {
      expect(_item(quantity: 3, unitPrice: 150.5).lineTotal, closeTo(451.5, 1e-9));
    });

    test('defaults to one unit called وحدة', () {
      final item = QuoteItem.create(quoteId: 1, description: 'لوح');
      expect(item.quantity, 1);
      expect(item.unitPrice, 0);
      expect(item.unit, 'وحدة');
      expect(item.lineTotal, 0);
    });

    test('keeps unitPrice through toMap/fromMap', () {
      final item = _item(quantity: 2, unitPrice: 75.25, unit: 'لوح')
          .copyWith(id: 9);
      final roundTripped = QuoteItem.fromMap(item.toMap());
      expect(roundTripped, equals(item));
      expect(roundTripped.unitPrice, 75.25);
      expect(roundTripped.unit, 'لوح');
    });

    test('fromMap tolerates rows created before the unitPrice migration', () {
      final legacy = <String, dynamic>{
        'id': 3,
        'quoteId': 1,
        'description': 'إنفرتر',
        'quantity': 1,
        'originCountry': null,
        'warranty': null,
        'orderIndex': 0,
      };
      final item = QuoteItem.fromMap(legacy);
      expect(item.unitPrice, 0);
      expect(item.unit, 'وحدة');
    });
  });
}
