import 'dart:typed_data';

import 'package:pdf/pdf.dart';
import 'package:pdf/widgets.dart' as pw;

import '../../features/customers/data/models/customer.dart';
import '../../features/designs/data/models/component.dart';
import '../../features/designs/data/models/design.dart';
import '../../features/quotes/data/models/quote.dart';
import '../../features/quotes/data/models/quote_item.dart';
import '../../features/quotes/data/models/term.dart';
import '../../features/quotes/domain/quote_totals.dart';
import '../../features/settings/data/models/app_settings.dart';
import '../utils/arabic_text.dart';
import '../utils/currency_formatter.dart';

/// Everything the PDF needs, gathered before generation starts.
///
/// Kept as a plain data holder so the generator itself stays a pure function of
/// its inputs (easy to test, no database access inside).
class QuotePdfData {
  final Quote quote;
  final Customer customer;
  final Design? design;
  final List<QuoteItem> items;
  final List<Term> terms;
  final AppSettings? settings;
  final Component? panel;
  final Component? inverter;

  /// Human friendly reference printed on the document, e.g. `Q-2026-0007`.
  final String quoteNumber;

  const QuotePdfData({
    required this.quote,
    required this.customer,
    this.design,
    required this.items,
    required this.terms,
    this.settings,
    this.panel,
    this.inverter,
    required this.quoteNumber,
  });

  QuoteTotals get totals => QuoteTotals.compute(
        items: items,
        discountPercent: quote.discount,
        taxPercent: quote.tax,
      );
}

/// Builds a right-to-left Arabic quotation PDF.
///
/// The `pdf` package draws one glyph per code point, so Arabic text has to be
/// pre-shaped into the presentation forms (see [ArabicText]) and the fonts must
/// contain Arabic glyphs (Amiri is bundled with the app).
class QuotePdfGenerator {
  QuotePdfGenerator({required this.baseFont, required this.boldFont});

  final pw.Font baseFont;
  final pw.Font boldFont;

  static const PdfColor _accent = PdfColor.fromInt(0xFF0B7A75);
  static const PdfColor _muted = PdfColor.fromInt(0xFF6B7280);

  /// Renders [data] and returns the bytes of the PDF document.
  Future<Uint8List> generate(QuotePdfData data) async {
    final document = pw.Document(
      title: 'عرض سعر ${data.quoteNumber}',
      author: data.settings?.companyName ?? 'SolarPro',
      creator: 'SolarPro',
      subject: 'عرض سعر رقم ${data.quoteNumber}',
      theme: pw.ThemeData.withFont(base: baseFont, bold: boldFont),
    );

    document.addPage(
      pw.MultiPage(
        pageFormat: PdfPageFormat.a4,
        textDirection: pw.TextDirection.rtl,
        margin: const pw.EdgeInsets.all(28),
        header: (context) => _buildHeader(data),
        footer: (context) => _buildFooter(context, data),
        build: (context) => [
          _buildParties(data),
          pw.SizedBox(height: 12),
          if (data.design != null) _buildSystemSummary(data),
          pw.SizedBox(height: 12),
          _buildItemsTable(data),
          pw.SizedBox(height: 10),
          _buildTotals(data),
          if (data.terms.isNotEmpty) ...[
            pw.SizedBox(height: 14),
            _buildTerms(data),
          ],
          pw.SizedBox(height: 18),
          _buildSignature(data),
        ],
      ),
    );

    return document.save();
  }

  // -------------------------------------------------------------------------
  // Building blocks
  // -------------------------------------------------------------------------

  pw.Widget _buildHeader(QuotePdfData data) {
    final company = data.settings?.companyName;
    final phone = data.settings?.companyPhone;

    return pw.Column(
      crossAxisAlignment: pw.CrossAxisAlignment.stretch,
      children: [
        pw.Row(
          mainAxisAlignment: pw.MainAxisAlignment.spaceBetween,
          crossAxisAlignment: pw.CrossAxisAlignment.start,
          children: [
            pw.Column(
              crossAxisAlignment: pw.CrossAxisAlignment.start,
              children: [
                _text(
                  company == null || company.isEmpty ? 'SolarPro' : company,
                  size: 16,
                  bold: true,
                ),
                if (phone != null && phone.isNotEmpty) _text('هاتف: $phone', size: 9, color: _muted),
              ],
            ),
            pw.Column(
              crossAxisAlignment: pw.CrossAxisAlignment.end,
              children: [
                _text('عرض سعر', size: 18, bold: true, color: _accent),
                _text('رقم العرض: ${data.quoteNumber}', size: 9),
                _text('التاريخ: ${_formatDate(data.quote.createdAt)}', size: 9),
              ],
            ),
          ],
        ),
        pw.SizedBox(height: 6),
        pw.Divider(thickness: 1.5, color: _accent),
        pw.SizedBox(height: 10),
      ],
    );
  }

  pw.Widget _buildFooter(pw.Context context, QuotePdfData data) {
    return pw.Row(
      mainAxisAlignment: pw.MainAxisAlignment.spaceBetween,
      children: [
        _text(
          'شكراً لثقتكم بنا — تم إنشاء هذا العرض عبر تطبيق SolarPro',
          size: 8,
          color: _muted,
        ),
        _text(
          'صفحة ${context.pageNumber} من ${context.pagesCount}',
          size: 8,
          color: _muted,
        ),
      ],
    );
  }

  pw.Widget _buildParties(QuotePdfData data) {
    return pw.Row(
      crossAxisAlignment: pw.CrossAxisAlignment.start,
      children: [
        pw.Expanded(
          child: _infoCard(
            title: 'بيانات العميل',
            rows: [
              ['الاسم', data.customer.name],
              if (data.customer.phone != null && data.customer.phone!.isNotEmpty)
                ['الهاتف', data.customer.phone!],
              if (data.customer.address != null && data.customer.address!.isNotEmpty)
                ['العنوان', data.customer.address!],
            ],
          ),
        ),
        pw.SizedBox(width: 12),
        pw.Expanded(
          child: _infoCard(
            title: 'بيانات العرض',
            rows: [
              ['الحالة', _statusLabel(data.quote.status)],
              ['عدد الأصناف', data.items.length.toString()],
              [
                'السعة',
                data.design != null
                    ? '${_trim(data.design!.capacityKw)} ك.و'
                    : '—',
              ],
            ],
          ),
        ),
      ],
    );
  }

  pw.Widget _infoCard({
    required String title,
    required List<List<String>> rows,
  }) {
    return pw.Container(
      padding: const pw.EdgeInsets.all(8),
      decoration: pw.BoxDecoration(
        border: pw.Border.all(color: PdfColors.grey300, width: 0.5),
        borderRadius: const pw.BorderRadius.all(pw.Radius.circular(4)),
      ),
      child: pw.Column(
        crossAxisAlignment: pw.CrossAxisAlignment.stretch,
        children: [
          _text(title, size: 11, bold: true, color: _accent),
          pw.SizedBox(height: 6),
          for (final row in rows)
            pw.Padding(
              padding: const pw.EdgeInsets.symmetric(vertical: 1.5),
              child: pw.Row(
                mainAxisAlignment: pw.MainAxisAlignment.spaceBetween,
                children: [
                  _text(row[1], size: 9),
                  _text(row[0], size: 9, color: _muted),
                ],
              ),
            ),
        ],
      ),
    );
  }

  pw.Widget _buildSystemSummary(QuotePdfData data) {
    final design = data.design!;
    final panel = data.panel;
    final inverter = data.inverter;

    return pw.Container(
      padding: const pw.EdgeInsets.all(8),
      decoration: pw.BoxDecoration(
        color: PdfColor.fromInt(0xFFF1F5F4),
        borderRadius: const pw.BorderRadius.all(pw.Radius.circular(4)),
      ),
      child: pw.Column(
        crossAxisAlignment: pw.CrossAxisAlignment.stretch,
        children: [
          _text('مواصفات النظام', size: 11, bold: true, color: _accent),
          pw.SizedBox(height: 6),
          _summaryRow('السعة', '${_trim(design.capacityKw)} ك.و'),
          _summaryRow('نوع النظام', _systemTypeLabel(design.systemType)),
          _summaryRow('عدد الألواح', '${design.panelCount} لوح'),
          _summaryRow('عدد السلاسل', '${design.stringCount} سلسلة'),
          _summaryRow('ألواح في السلسلة', '${design.panelsPerString}'),
          if (panel != null)
            _summaryRow(
              'اللوح',
              '${panel.brand} ${panel.model} (${panel.powerW ?? 0} واط)',
            ),
          if (inverter != null)
            _summaryRow(
              'الإنفرتر',
              '${inverter.brand} ${inverter.model} (${_trim(inverter.powerKw ?? 0)} ك.و)',
            ),
        ],
      ),
    );
  }

  pw.Widget _summaryRow(String label, String value) {
    return pw.Padding(
      padding: const pw.EdgeInsets.symmetric(vertical: 1.5),
      child: pw.Row(
        mainAxisAlignment: pw.MainAxisAlignment.spaceBetween,
        children: [
          _text(value, size: 9),
          _text(label, size: 9, color: _muted),
        ],
      ),
    );
  }

  pw.Widget _buildItemsTable(QuotePdfData data) {
    final headerStyle = pw.TextStyle(
      font: boldFont,
      fontSize: 9,
      color: PdfColors.white,
    );

    pw.Widget headerCell(String label) => pw.Padding(
          padding: const pw.EdgeInsets.all(5),
          child: pw.Text(
            ArabicText.reshape(label),
            style: headerStyle,
            textDirection: pw.TextDirection.rtl,
          ),
        );

    return pw.Table(
      border: pw.TableBorder.all(color: PdfColors.grey300, width: 0.5),
      columnWidths: const <int, pw.TableColumnWidth>{
        0: pw.FixedColumnWidth(22),
        1: pw.FlexColumnWidth(4),
        2: pw.FixedColumnWidth(38),
        3: pw.FlexColumnWidth(2),
        4: pw.FlexColumnWidth(2),
        5: pw.FlexColumnWidth(2),
      },
      children: [
        pw.TableRow(
          decoration: const pw.BoxDecoration(color: _accent),
          children: [
            headerCell('م'),
            headerCell('البيان'),
            headerCell('الكمية'),
            headerCell('سعر الوحدة'),
            headerCell('الإجمالي'),
            headerCell('الضمان'),
          ],
        ),
        for (var i = 0; i < data.items.length; i++)
          pw.TableRow(
            decoration: pw.BoxDecoration(
              color: i.isOdd
                  ? PdfColor.fromInt(0xFFF7F9F9)
                  : PdfColor.fromInt(0xFFFFFFFF),
            ),
            children: _itemCells(data.items[i], i + 1),
          ),
      ],
    );
  }

  List<pw.Widget> _itemCells(QuoteItem item, int index) {
    final extras = <String>[
      if (item.originCountry != null && item.originCountry!.isNotEmpty)
        'بلد المنشأ: ${item.originCountry!}',
    ];

    return [
      _cell(_text('$index', size: 9, align: pw.TextAlign.center)),
      _cell(
        pw.Column(
          crossAxisAlignment: pw.CrossAxisAlignment.start,
          children: [
            _text(item.description, size: 9, bold: true),
            if (extras.isNotEmpty)
              _text(extras.join(' · '), size: 7.5, color: _muted),
          ],
        ),
      ),
      _cell(
        _text(
          '${item.quantity} ${item.unit}',
          size: 9,
          align: pw.TextAlign.center,
        ),
      ),
      _cell(
        _text(
          CurrencyFormatter.number(item.unitPrice),
          size: 9,
          align: pw.TextAlign.center,
        ),
      ),
      _cell(
        _text(
          CurrencyFormatter.number(item.lineTotal),
          size: 9,
          align: pw.TextAlign.center,
          bold: true,
        ),
      ),
      _cell(
        _text(
          item.warranty ?? '—',
          size: 8,
          align: pw.TextAlign.center,
          color: item.warranty == null ? _muted : PdfColors.black,
        ),
      ),
    ];
  }

  pw.Widget _cell(pw.Widget child) => pw.Padding(
        padding: const pw.EdgeInsets.all(5),
        child: child,
      );

  pw.Widget _buildTotals(QuotePdfData data) {
    final totals = data.totals;

    pw.Widget totalRow(String label, String value, {bool highlight = false}) {
      return pw.Padding(
        padding: const pw.EdgeInsets.symmetric(vertical: 2),
        child: pw.Row(
          mainAxisAlignment: pw.MainAxisAlignment.spaceBetween,
          children: [
            _text(
              value,
              size: highlight ? 12 : 9.5,
              bold: highlight,
              color: highlight ? _accent : PdfColors.black,
            ),
            _text(
              label,
              size: highlight ? 12 : 9.5,
              bold: highlight,
              color: highlight ? _accent : _muted,
            ),
          ],
        ),
      );
    }

    return pw.Align(
      alignment: pw.Alignment.centerLeft,
      child: pw.Container(
        width: 260,
        padding: const pw.EdgeInsets.all(8),
        decoration: pw.BoxDecoration(
          border: pw.Border.all(color: PdfColors.grey300, width: 0.5),
          borderRadius: const pw.BorderRadius.all(pw.Radius.circular(4)),
        ),
        child: pw.Column(
          children: [
            totalRow('المجموع الفرعي', CurrencyFormatter.money(totals.subtotal)),
            if (totals.discountPercent > 0)
              totalRow(
                'الخصم (${_trim(totals.discountPercent)}%)',
                '- ${CurrencyFormatter.money(totals.discountAmount)}',
              ),
            if (totals.taxPercent > 0)
              totalRow(
                'الضريبة (${_trim(totals.taxPercent)}%)',
                CurrencyFormatter.money(totals.taxAmount),
              ),
            pw.Divider(thickness: 0.5, color: PdfColors.grey400),
            totalRow(
              'الإجمالي المستحق',
              CurrencyFormatter.money(totals.total),
              highlight: true,
            ),
          ],
        ),
      ),
    );
  }

  pw.Widget _buildTerms(QuotePdfData data) {
    return pw.Column(
      crossAxisAlignment: pw.CrossAxisAlignment.stretch,
      children: [
        _text('الشروط والأحكام', size: 11, bold: true, color: _accent),
        pw.SizedBox(height: 5),
        for (var i = 0; i < data.terms.length; i++)
          pw.Padding(
            padding: const pw.EdgeInsets.symmetric(vertical: 1.5),
            child: pw.Row(
              crossAxisAlignment: pw.CrossAxisAlignment.start,
              children: [
                _text('${i + 1}.', size: 9, color: _muted),
                pw.SizedBox(width: 4),
                pw.Expanded(child: _text(data.terms[i].text, size: 9)),
              ],
            ),
          ),
      ],
    );
  }

  pw.Widget _buildSignature(QuotePdfData data) {
    return pw.Row(
      mainAxisAlignment: pw.MainAxisAlignment.spaceBetween,
      children: [
        pw.Column(
          crossAxisAlignment: pw.CrossAxisAlignment.center,
          children: [
            pw.SizedBox(height: 24),
            pw.Container(
              width: 140,
              decoration: const pw.BoxDecoration(
                border: pw.Border(top: pw.BorderSide(color: PdfColors.grey500)),
              ),
              child: pw.Padding(
                padding: const pw.EdgeInsets.only(top: 4),
                child: _text(
                  data.settings?.companyName?.isNotEmpty == true
                      ? data.settings!.companyName!
                      : 'الشركة',
                  size: 9,
                  align: pw.TextAlign.center,
                ),
              ),
            ),
          ],
        ),
        pw.Column(
          crossAxisAlignment: pw.CrossAxisAlignment.center,
          children: [
            pw.SizedBox(height: 24),
            pw.Container(
              width: 140,
              decoration: const pw.BoxDecoration(
                border: pw.Border(top: pw.BorderSide(color: PdfColors.grey500)),
              ),
              child: pw.Padding(
                padding: const pw.EdgeInsets.only(top: 4),
                child: _text(
                  'توقيع العميل: ${data.customer.name}',
                  size: 9,
                  align: pw.TextAlign.center,
                ),
              ),
            ),
          ],
        ),
      ],
    );
  }

  // -------------------------------------------------------------------------
  // Text helpers
  // -------------------------------------------------------------------------

  pw.Widget _text(
    String value, {
    double size = 10,
    bool bold = false,
    PdfColor? color,
    pw.TextAlign? align,
  }) {
    return pw.Text(
      ArabicText.reshape(value),
      textDirection: pw.TextDirection.rtl,
      textAlign: align,
      style: pw.TextStyle(
        font: bold ? boldFont : baseFont,
        fontSize: size,
        color: color,
      ),
    );
  }

  static String _formatDate(DateTime date) {
    final d = date.toLocal();
    return '${d.year}/${_pad(d.month)}/${_pad(d.day)}';
  }

  static String _pad(int value) => value.toString().padLeft(2, '0');

  /// Prints a double without a trailing `.0` when it is a whole number.
  static String _trim(double value) {
    if (value == value.roundToDouble()) return value.toStringAsFixed(0);
    return value.toStringAsFixed(2);
  }

  static String _statusLabel(String status) {
    switch (status) {
      case 'draft':
        return 'مسودة';
      case 'sent':
        return 'مرسل';
      case 'accepted':
        return 'مقبول';
      case 'rejected':
        return 'مرفوض';
      case 'expired':
        return 'منتهي';
      default:
        return status;
    }
  }

  static String _systemTypeLabel(String type) {
    switch (type) {
      case 'on_grid':
        return 'شبكي (On-Grid)';
      case 'off_grid':
        return 'غير شبكي (Off-Grid)';
      case 'hybrid':
        return 'هجين (Hybrid)';
      default:
        return type;
    }
  }
}
