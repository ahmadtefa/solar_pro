import 'dart:io';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:pdf/widgets.dart' as pw;
import 'package:solar_pro/core/pdf/quote_pdf.dart';
import 'package:solar_pro/features/customers/data/models/customer.dart';
import 'package:solar_pro/features/designs/data/models/component.dart';
import 'package:solar_pro/features/designs/data/models/design.dart';
import 'package:solar_pro/features/quotes/data/models/quote.dart';
import 'package:solar_pro/features/quotes/data/models/quote_item.dart';
import 'package:solar_pro/features/quotes/data/models/term.dart';
import 'package:solar_pro/features/settings/data/models/app_settings.dart';

void main() {
  final customer = Customer(
    id: 1,
    name: 'شركة النور للطاقة',
    phone: '01012345678',
    address: 'المنيا - مصر',
    createdAt: DateTime(2026, 10, 1),
  );

  final design = Design(
    id: 5,
    customerId: 1,
    capacityKw: 10,
    systemType: 'on_grid',
    customerType: 'commercial',
    panelId: 21,
    inverterId: 22,
    panelCount: 18,
    stringCount: 2,
    panelsPerString: 9,
    createdAt: DateTime(2026, 10, 5),
  );

  final panel = Component(
    id: 21,
    type: 'panel',
    brand: 'Longi',
    model: 'Hi-MO 6',
    pricePerWatt: 6.8,
    powerW: 580,
    vocV: 51.2,
    createdAt: DateTime(2026, 10, 1),
  );

  final inverter = Component(
    id: 22,
    type: 'inverter',
    brand: 'Sungrow',
    model: 'SG10RT',
    price: 45000,
    powerKw: 10,
    maxDcVoltage: 1100,
    createdAt: DateTime(2026, 10, 1),
  );

  const settings = AppSettings(
    id: 1,
    companyName: 'SolarPro مصر',
    companyPhone: '01000000000',
    defaultPricePerKw: 2500,
  );

  QuotePdfData buildData({List<QuoteItem>? items}) {
    final quote = Quote(
      id: 7,
      designId: design.id!,
      customerId: customer.id!,
      discount: 5,
      tax: 14,
      status: QuoteStatus.sent.value,
      createdAt: DateTime(2026, 10, 7),
    );
    return QuotePdfData(
      quote: quote,
      customer: customer,
      design: design,
      items: items ??
          <QuoteItem>[
            QuoteItem.create(
              quoteId: 7,
              description: 'ألواح شمسية Longi 580 واط',
              quantity: 18,
              unitPrice: 3944,
              unit: 'لوح',
              originCountry: 'الصين',
              warranty: '10 سنوات',
            ),
            QuoteItem.create(
              quoteId: 7,
              description: 'إنفرتر Sungrow 10 ك.و',
              quantity: 1,
              unitPrice: 45000,
              unit: 'جهاز',
            ),
          ],
      terms: <Term>[
        Term.create(quoteId: 7, text: 'الأسعار تشمل التوريد والتركيب.'),
      ],
      settings: settings,
      panel: panel,
      inverter: inverter,
      quoteNumber: quote.displayNumber,
    );
  }

  test('the quote number is stable and readable', () {
    expect(buildData().quoteNumber, 'Q-2026-0007');
  });

  test('totals are derived from the items', () {
    final totals = buildData().totals;
    // 18 * 3944 + 45000 = 115992
    // 18 x 3944 + 45,000 = 115,992
    expect(totals.subtotal, closeTo(115992, 1e-9));
    // 5% of 115,992 = 5,799.6 ; 14% of 110,192.4 = 15,426.936
    expect(totals.discountAmount, closeTo(5799.6, 1e-6));
    expect(totals.taxAmount, closeTo(15426.936, 1e-3));
    expect(totals.total, closeTo(125619.336, 1e-3));
  });

  test('builds a real PDF document with the bundled Arabic font',
      () async {
    final regular = File('assets/fonts/Amiri-Regular.ttf');
    final bold = File('assets/fonts/Amiri-Bold.ttf');
    if (!regular.existsSync() || !bold.existsSync()) {
      // Fonts are bundled with the app; skip when running from a clean checkout
      // without the asset directory.
      return;
    }

    final generator = QuotePdfGenerator(
      baseFont: pw.Font.ttf(ByteData.sublistView(regular.readAsBytesSync())),
      boldFont: pw.Font.ttf(ByteData.sublistView(bold.readAsBytesSync())),
    );

    final bytes = await generator.generate(buildData());

    expect(bytes.lengthInBytes, greaterThan(2000));
    expect(String.fromCharCodes(bytes.take(5)), '%PDF-');
    // Every PDF ends with the EOF marker.
    final tail = String.fromCharCodes(
      bytes.sublist(bytes.lengthInBytes - 32),
    );
    expect(tail, contains('%%EOF'));
  });

  test('an empty quote still produces a document', () async {
    final regular = File('assets/fonts/Amiri-Regular.ttf');
    final bold = File('assets/fonts/Amiri-Bold.ttf');
    if (!regular.existsSync() || !bold.existsSync()) return;

    final generator = QuotePdfGenerator(
      baseFont: pw.Font.ttf(ByteData.sublistView(regular.readAsBytesSync())),
      boldFont: pw.Font.ttf(ByteData.sublistView(bold.readAsBytesSync())),
    );

    final bytes = await generator.generate(buildData(items: <QuoteItem>[]));
    expect(bytes.lengthInBytes, greaterThan(1000));
    expect(String.fromCharCodes(bytes.take(5)), '%PDF-');
  });
}
