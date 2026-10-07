import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:printing/printing.dart';

import '../../../../core/pdf/pdf_fonts.dart';
import '../../../../core/pdf/quote_pdf.dart';
import '../../../../core/utils/currency_formatter.dart';
import '../../../customers/data/models/customer.dart';
import '../../../customers/presentation/providers/customer_providers.dart';
import '../../../designs/data/models/component.dart';
import '../../../designs/data/models/design.dart';
import '../../../designs/presentation/providers/component_providers.dart';
import '../../../designs/presentation/providers/design_providers.dart';
import '../../../projects/data/models/project.dart';
import '../../../settings/data/models/app_settings.dart';
import '../../../settings/presentation/providers/settings_providers.dart';
import '../../data/models/quote.dart';
import '../../data/models/quote_item.dart';
import '../../data/models/term.dart';
import '../../domain/quote_totals.dart';
import '../providers/quote_providers.dart';
import '../widgets/quote_status_badge.dart';
import 'quote_form_screen.dart';

/// Shows a single quotation: parties, items, totals, terms, and the actions
/// that can be taken on it (print to PDF, convert to a project, change status).
class QuoteDetailsScreen extends ConsumerStatefulWidget {
  const QuoteDetailsScreen({super.key, required this.quote});

  final Quote quote;

  @override
  ConsumerState<QuoteDetailsScreen> createState() => _QuoteDetailsScreenState();
}

class _QuoteDetailsScreenState extends ConsumerState<QuoteDetailsScreen> {
  bool _working = false;

  @override
  Widget build(BuildContext context) {
    final quote = widget.quote;
    final quoteId = quote.id ?? 0;

    final freshQuote = ref.watch(quoteByIdProvider(quoteId));
    final current = freshQuote.valueOrNull ?? quote;

    final customerAsync = ref.watch(customerByIdProvider(current.customerId));
    final designAsync = ref.watch(designByIdProvider(current.designId));
    final itemsAsync = ref.watch(quoteItemsProvider(quoteId));
    final termsAsync = ref.watch(quoteTermsProvider(quoteId));
    final projectAsync = ref.watch(projectForQuoteProvider(quoteId));
    final settingsAsync = ref.watch(settingsProvider);

    final design = designAsync.valueOrNull;
    final panelAsync =
        ref.watch(componentByIdProvider(design?.panelId ?? 0));
    final inverterAsync =
        ref.watch(componentByIdProvider(design?.inverterId ?? 0));

    final items = itemsAsync.valueOrNull ?? <QuoteItem>[];
    final terms = termsAsync.valueOrNull ?? <Term>[];
    final totals = QuoteTotals.compute(
      items: items,
      discountPercent: current.discount,
      taxPercent: current.tax,
    );

    return Scaffold(
      appBar: AppBar(
        title: Text('عرض سعر ${current.displayNumber}'),
        actions: [
          IconButton(
            tooltip: 'تعديل',
            icon: const Icon(Icons.edit),
            onPressed: () => _openForm(context, current),
          ),
          IconButton(
            tooltip: 'حذف',
            icon: const Icon(Icons.delete_outline),
            onPressed: () => _confirmDelete(context, current),
          ),
        ],
      ),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(16, 12, 16, 100),
        children: [
          Row(
            children: [
              QuoteStatusBadge(status: current.status),
              const Spacer(),
              _buildStatusMenu(current),
            ],
          ),
          const SizedBox(height: 12),
          _customerCard(customerAsync.valueOrNull),
          const SizedBox(height: 12),
          _designCard(design, panelAsync.valueOrNull, inverterAsync.valueOrNull),
          const SizedBox(height: 12),
          _itemsCard(items),
          const SizedBox(height: 12),
          _totalsCard(totals),
          if (terms.isNotEmpty) ...[
            const SizedBox(height: 12),
            _termsCard(terms),
          ],
          const SizedBox(height: 12),
          _projectCard(projectAsync.valueOrNull, projectAsync.isLoading),
          const SizedBox(height: 20),
          _actionsRow(
            context,
            quote: current,
            customer: customerAsync.valueOrNull,
            design: design,
            items: items,
            terms: terms,
            settings: settingsAsync.valueOrNull,
            panel: panelAsync.valueOrNull,
            inverter: inverterAsync.valueOrNull,
          ),
        ],
      ),
    );
  }

  // ---------------------------------------------------------------------------
  // Cards
  // ---------------------------------------------------------------------------

  Widget _buildStatusMenu(Quote quote) {
    return PopupMenuButton<String>(
      enabled: !_working,
      onSelected: (status) => _changeStatus(quote, status),
      itemBuilder: (context) => [
        for (final status in QuoteStatus.values)
          PopupMenuItem<String>(
            value: status.value,
            child: Text(status.labelAr),
          ),
      ],
      child: Chip(
        avatar: const Icon(Icons.swap_horiz, size: 16),
        label: const Text('تغيير الحالة'),
      ),
    );
  }

  Widget _customerCard(Customer? customer) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            _cardTitle('بيانات العميل'),
            const SizedBox(height: 6),
            _infoRow('الاسم', customer?.name ?? '—'),
            if (customer?.phone?.isNotEmpty == true)
              _infoRow('الهاتف', customer!.phone!),
            if (customer?.address?.isNotEmpty == true)
              _infoRow('العنوان', customer!.address!),
          ],
        ),
      ),
    );
  }

  Widget _designCard(Design? design, Component? panel, Component? inverter) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            _cardTitle('مواصفات النظام'),
            const SizedBox(height: 6),
            if (design == null)
              const Text('لا يوجد تصميم مرتبط بهذا العرض.')
            else ...[
              _infoRow('السعة', '${_trim(design.capacityKw)} ك.و'),
              _infoRow('عدد الألواح', '${design.panelCount} لوح'),
              _infoRow('عدد السلاسل', '${design.stringCount}'),
              _infoRow('ألواح/سلسلة', '${design.panelsPerString}'),
              if (panel != null)
                _infoRow('اللوح', '${panel.brand} ${panel.model}'),
              if (inverter != null)
                _infoRow('الإنفرتر', '${inverter.brand} ${inverter.model}'),
            ],
          ],
        ),
      ),
    );
  }

  Widget _itemsCard(List<QuoteItem> items) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            _cardTitle('الأصناف (${items.length})'),
            const SizedBox(height: 6),
            if (items.isEmpty)
              const Text('لا توجد أصناف مسجلة في هذا العرض.')
            else
              for (var i = 0; i < items.length; i++) ...[
                if (i > 0) const Divider(height: 16),
                Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    CircleAvatar(
                      radius: 12,
                      child: Text('${i + 1}', style: const TextStyle(fontSize: 12)),
                    ),
                    const SizedBox(width: 8),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            items[i].description,
                            style: const TextStyle(fontWeight: FontWeight.w600),
                          ),
                          const SizedBox(height: 2),
                          Text(
                            '${items[i].quantity} ${items[i].unit} × '
                            '${CurrencyFormatter.number(items[i].unitPrice)}',
                            style: TextStyle(
                              fontSize: 12,
                              color: Theme.of(context).colorScheme.outline,
                            ),
                          ),
                          if (items[i].originCountry != null ||
                              items[i].warranty != null)
                            Text(
                              [
                                if (items[i].originCountry != null)
                                  'المنشأ: ${items[i].originCountry}',
                                if (items[i].warranty != null)
                                  'الضمان: ${items[i].warranty}',
                              ].join(' · '),
                              style: TextStyle(
                                fontSize: 12,
                                color: Theme.of(context).colorScheme.outline,
                              ),
                            ),
                        ],
                      ),
                    ),
                    Text(
                      CurrencyFormatter.money(items[i].lineTotal),
                      style: const TextStyle(fontWeight: FontWeight.bold),
                    ),
                  ],
                ),
              ],
          ],
        ),
      ),
    );
  }

  Widget _totalsCard(QuoteTotals totals) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          children: [
            _infoRow('المجموع الفرعي', CurrencyFormatter.money(totals.subtotal)),
            if (totals.discountPercent > 0)
              _infoRow(
                'الخصم (${_trim(totals.discountPercent)}%)',
                '- ${CurrencyFormatter.money(totals.discountAmount)}',
              ),
            if (totals.taxPercent > 0)
              _infoRow(
                'الضريبة (${_trim(totals.taxPercent)}%)',
                CurrencyFormatter.money(totals.taxAmount),
              ),
            const Divider(),
            _infoRow(
              'الإجمالي المستحق',
              CurrencyFormatter.money(totals.total),
              bold: true,
            ),
          ],
        ),
      ),
    );
  }

  Widget _termsCard(List<Term> terms) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            _cardTitle('الشروط والأحكام'),
            const SizedBox(height: 6),
            for (var i = 0; i < terms.length; i++)
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 2),
                child: Text('${i + 1}. ${terms[i].text}'),
              ),
          ],
        ),
      ),
    );
  }

  Widget _projectCard(Project? project, bool loading) {
    if (loading) {
      return const Card(child: Padding(
        padding: EdgeInsets.all(12),
        child: LinearProgressIndicator(),
      ));
    }
    if (project == null) return const SizedBox.shrink();
    final id = project.id;
    final status = project.status;
    return Card(
      color: Theme.of(context).colorScheme.primaryContainer.withValues(alpha: 0.35),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Row(
          children: [
            Icon(Icons.construction,
                color: Theme.of(context).colorScheme.primary),
            const SizedBox(width: 8),
            Expanded(
              child: Text(
                'تم تحويل العرض إلى مشروع${id != null ? ' رقم #$id' : ''}'
                ' (الحالة: ${_projectStatusLabel(status)})',
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _actionsRow(
    BuildContext context, {
    required Quote quote,
    Customer? customer,
    Design? design,
    required List<QuoteItem> items,
    required List<Term> terms,
    AppSettings? settings,
    Component? panel,
    Component? inverter,
  }) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        FilledButton.icon(
          onPressed: _working
              ? null
              : () => _sharePdf(
                    quote: quote,
                    customer: customer,
                    design: design,
                    items: items,
                    terms: terms,
                    settings: settings,
                    panel: panel,
                    inverter: inverter,
                  ),
          icon: const Icon(Icons.picture_as_pdf),
          label: const Text('إنشاء PDF ومشاركته'),
        ),
        const SizedBox(height: 8),
        OutlinedButton.icon(
          onPressed: _working
              ? null
              : () => _printPdf(
                    quote: quote,
                    customer: customer,
                    design: design,
                    items: items,
                    terms: terms,
                    settings: settings,
                    panel: panel,
                    inverter: inverter,
                  ),
          icon: const Icon(Icons.print),
          label: const Text('طباعة'),
        ),
        const SizedBox(height: 8),
        OutlinedButton.icon(
          onPressed: _working ? null : () => _convertToProject(quote),
          icon: const Icon(Icons.construction),
          label: const Text('تحويل إلى مشروع'),
        ),
      ],
    );
  }

  Widget _cardTitle(String title) {
    return Text(
      title,
      style: Theme.of(context).textTheme.titleMedium?.copyWith(
            fontWeight: FontWeight.bold,
            color: Theme.of(context).colorScheme.primary,
          ),
    );
  }

  Widget _infoRow(String label, String value, {bool bold = false}) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 3),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Expanded(
            child: Text(
              value,
              textAlign: TextAlign.start,
              style: TextStyle(fontWeight: bold ? FontWeight.bold : FontWeight.normal),
            ),
          ),
          const SizedBox(width: 8),
          Text(
            label,
            style: TextStyle(
              color: Theme.of(context).colorScheme.outline,
              fontWeight: bold ? FontWeight.bold : FontWeight.normal,
            ),
          ),
        ],
      ),
    );
  }

  // ---------------------------------------------------------------------------
  // Actions
  // ---------------------------------------------------------------------------

  Future<void> _openForm(BuildContext context, Quote quote) async {
    await Navigator.of(context).push(
      MaterialPageRoute(builder: (_) => QuoteFormScreen(quote: quote)),
    );
    if (mounted) ref.invalidate(quotesListProvider);
  }

  Future<void> _changeStatus(Quote quote, String status) async {
    final id = quote.id;
    if (id == null) return;
    setState(() => _working = true);
    await ref.read(quotesListProvider.notifier).updateStatus(id, status);
    if (mounted) setState(() => _working = false);
  }

  Future<void> _convertToProject(Quote quote) async {
    final id = quote.id;
    if (id == null) return;
    setState(() => _working = true);
    try {
      final projectId =
          await ref.read(quotesListProvider.notifier).convertToProject(id);
      if (!mounted) return;
      _message(
        projectId == null
            ? 'تم تحويل هذا العرض إلى مشروع من قبل'
            : 'تم إنشاء المشروع رقم #$projectId بنجاح',
      );
    } catch (error) {
      if (mounted) _message('تعذر التحويل: $error');
    } finally {
      if (mounted) setState(() => _working = false);
    }
  }

  Future<void> _confirmDelete(BuildContext context, Quote quote) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('حذف عرض السعر'),
        content: Text(
          'سيتم حذف العرض رقم "${quote.displayNumber}" نهائياً.\n'
          'لا يمكن التراجع عن هذه العملية.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(false),
            child: const Text('إلغاء'),
          ),
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(true),
            style: TextButton.styleFrom(foregroundColor: Colors.red),
            child: const Text('حذف'),
          ),
        ],
      ),
    );

    if (confirmed != true) return;
    await ref.read(quotesListProvider.notifier).deleteQuote(quote.id!);
    // `context` is the parameter of this helper, so it needs its own check.
    if (context.mounted) Navigator.of(context).pop(true);
  }

  QuotePdfData _pdfData({
    required Quote quote,
    Customer? customer,
    Design? design,
    required List<QuoteItem> items,
    required List<Term> terms,
    AppSettings? settings,
    Component? panel,
    Component? inverter,
  }) {
    return QuotePdfData(
      quote: quote,
      customer: customer ??
          Customer(
            name: 'عميل غير معروف',
            createdAt: DateTime.now(),
          ),
      design: design,
      items: items,
      terms: terms,
      settings: settings,
      panel: panel,
      inverter: inverter,
      quoteNumber: quote.displayNumber,
    );
  }

  Future<Uint8List> _buildPdf(QuotePdfData data) async {
    final fonts = await PdfFontLoader.loadArabic();
    final generator = QuotePdfGenerator(
      baseFont: fonts.base,
      boldFont: fonts.bold,
    );
    return generator.generate(data);
  }

  Future<void> _sharePdf({
    required Quote quote,
    Customer? customer,
    Design? design,
    required List<QuoteItem> items,
    required List<Term> terms,
    AppSettings? settings,
    Component? panel,
    Component? inverter,
  }) async {
    setState(() => _working = true);
    try {
      final bytes = await _buildPdf(
        _pdfData(
          quote: quote,
          customer: customer,
          design: design,
          items: items,
          terms: terms,
          settings: settings,
          panel: panel,
          inverter: inverter,
        ),
      );
      await Printing.sharePdf(
        bytes: bytes,
        filename: 'quote-${quote.displayNumber}.pdf',
      );
    } catch (error) {
      if (mounted) _message('تعذر إنشاء ملف PDF: $error');
    } finally {
      if (mounted) setState(() => _working = false);
    }
  }

  Future<void> _printPdf({
    required Quote quote,
    Customer? customer,
    Design? design,
    required List<QuoteItem> items,
    required List<Term> terms,
    AppSettings? settings,
    Component? panel,
    Component? inverter,
  }) async {
    setState(() => _working = true);
    try {
      final bytes = await _buildPdf(
        _pdfData(
          quote: quote,
          customer: customer,
          design: design,
          items: items,
          terms: terms,
          settings: settings,
          panel: panel,
          inverter: inverter,
        ),
      );
      await Printing.layoutPdf(onLayout: (_) async => bytes);
    } catch (error) {
      if (mounted) _message('تعذر الطباعة: $error');
    } finally {
      if (mounted) setState(() => _working = false);
    }
  }

  void _message(String text) {
    ScaffoldMessenger.of(context)
      ..clearSnackBars()
      ..showSnackBar(SnackBar(content: Text(text)));
  }

  static String _trim(double value) {
    if (value == value.roundToDouble()) return value.toStringAsFixed(0);
    return value.toStringAsFixed(2);
  }

  static String _projectStatusLabel(String status) {
    switch (status) {
      case 'pending':
        return 'قيد الانتظار';
      case 'in_progress':
        return 'جاري التنفيذ';
      case 'completed':
        return 'مكتمل';
      case 'cancelled':
        return 'ملغي';
      default:
        return status;
    }
  }
}
