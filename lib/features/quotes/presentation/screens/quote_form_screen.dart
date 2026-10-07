import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../../core/utils/currency_formatter.dart';
import '../../../designs/data/models/component.dart';
import '../../../designs/data/models/design.dart';
import '../../../designs/presentation/providers/component_providers.dart';
import '../../../designs/presentation/providers/design_providers.dart';
import '../../../settings/presentation/providers/settings_providers.dart';
import '../../data/models/quote.dart';
import '../../data/models/quote_item.dart';
import '../../data/models/term.dart';
import '../../domain/quote_totals.dart';
import '../providers/quote_providers.dart';
import '../widgets/quote_status_badge.dart';

/// Units the user can pick for a quote line.
const List<String> kQuoteUnits = <String>[
  'وحدة',
  'لوح',
  'جهاز',
  'متر',
  'طقم',
  'خدمة',
];

/// Terms offered as a one-tap starting point.
const List<String> kDefaultTerms = <String>[
  'الأسعار تشمل التوريد والتركيب.',
  'مدة التنفيذ 15 يوم عمل من تاريخ التعاقد.',
  'الضمان 10 سنوات على الألواح و5 سنوات على الإنفرتر.',
  'صلاحية العرض 30 يوماً من تاريخه.',
];

/// Text controllers of a single editable quote line.
class _LineFields {
  _LineFields({
    String description = '',
    String quantity = '1',
    String unitPrice = '',
    String originCountry = '',
    String warranty = '',
    this.unit = 'وحدة',
  })  : descriptionController = TextEditingController(text: description),
        quantityController = TextEditingController(text: quantity),
        unitPriceController = TextEditingController(text: unitPrice),
        originController = TextEditingController(text: originCountry),
        warrantyController = TextEditingController(text: warranty);

  final TextEditingController descriptionController;
  final TextEditingController quantityController;
  final TextEditingController unitPriceController;
  final TextEditingController originController;
  final TextEditingController warrantyController;
  String unit;

  bool get isEmpty =>
      descriptionController.text.trim().isEmpty &&
      (double.tryParse(unitPriceController.text.trim()) ?? 0) <= 0;

  QuoteItem toItem(int quoteId, int index) {
    return QuoteItem.create(
      quoteId: quoteId,
      description: descriptionController.text.trim(),
      quantity: int.tryParse(quantityController.text.trim()) ?? 1,
      unitPrice: double.tryParse(unitPriceController.text.trim()) ?? 0,
      unit: unit,
      originCountry: _nullIfEmpty(originController.text),
      warranty: _nullIfEmpty(warrantyController.text),
      orderIndex: index,
    );
  }

  void dispose() {
    descriptionController.dispose();
    quantityController.dispose();
    unitPriceController.dispose();
    originController.dispose();
    warrantyController.dispose();
  }
}

String? _nullIfEmpty(String value) {
  final trimmed = value.trim();
  return trimmed.isEmpty ? null : trimmed;
}

/// Creates a new quote or edits an existing one.
class QuoteFormScreen extends ConsumerStatefulWidget {
  const QuoteFormScreen({super.key, this.quote});

  /// When non-null the screen edits this quote instead of creating a new one.
  final Quote? quote;

  @override
  ConsumerState<QuoteFormScreen> createState() => _QuoteFormScreenState();
}

class _QuoteFormScreenState extends ConsumerState<QuoteFormScreen> {
  final _formKey = GlobalKey<FormState>();
  final _discountController = TextEditingController(text: '0');
  final _taxController = TextEditingController(text: '0');

  final List<_LineFields> _items = <_LineFields>[];
  final List<TextEditingController> _terms = <TextEditingController>[];

  int? _selectedCustomerId;
  int? _selectedDesignId;
  String _selectedStatus = QuoteStatus.draft.value;
  bool _saving = false;
  bool _childrenLoaded = false;

  bool get _isEditing => widget.quote != null;

  @override
  void initState() {
    super.initState();

    if (_isEditing) {
      final quote = widget.quote!;
      _selectedCustomerId = quote.customerId;
      _selectedDesignId = quote.designId;
      _selectedStatus = quote.status;
      _discountController.text = _trimNumber(quote.discount);
      _taxController.text = _trimNumber(quote.tax);
    } else {
      _items.add(_LineFields());
    }

    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      if (_isEditing) {
        _loadChildren();
      } else if (_selectedCustomerId == null) {
        _preselectFirstCustomer();
      }
    });
  }

  /// Loads the items and terms of the edited quote once the providers are ready.
  Future<void> _loadChildren() async {
    final quoteId = widget.quote?.id;
    if (quoteId == null || _childrenLoaded) return;

    final items = await ref.read(quoteItemsProvider(quoteId).future);
    final terms = await ref.read(quoteTermsProvider(quoteId).future);
    if (!mounted || _childrenLoaded) return;

    setState(() {
      for (final item in items) {
        _items.add(
          _LineFields(
            description: item.description,
            quantity: item.quantity.toString(),
            unitPrice: item.unitPrice.toString(),
            originCountry: item.originCountry ?? '',
            warranty: item.warranty ?? '',
            unit: item.unit,
          ),
        );
      }
      for (final term in terms) {
        _terms.add(TextEditingController(text: term.text));
      }
      if (_items.isEmpty) _items.add(_LineFields());
      if (_terms.isEmpty) _terms.add(TextEditingController());
      _childrenLoaded = true;
    });
  }

  void _preselectFirstCustomer() {
    final customers = ref.read(customersForDropdownProvider).valueOrNull;
    if (customers == null || customers.isEmpty) return;
    setState(() => _selectedCustomerId = customers.first.id);
  }

  @override
  void dispose() {
    _discountController.dispose();
    _taxController.dispose();
    for (final line in _items) {
      line.dispose();
    }
    for (final controller in _terms) {
      controller.dispose();
    }
    super.dispose();
  }

  // ---------------------------------------------------------------------------
  // Derived values
  // ---------------------------------------------------------------------------

  List<QuoteItem> get _currentItems {
    final lines = _items.where((line) => !line.isEmpty).toList();
    return [
      for (var i = 0; i < lines.length; i++) lines[i].toItem(0, i),
    ];
  }

  QuoteTotals get _totals {
    return QuoteTotals.compute(
      items: _currentItems,
      discountPercent: double.tryParse(_discountController.text.trim()) ?? 0,
      taxPercent: double.tryParse(_taxController.text.trim()) ?? 0,
    );
  }

  // ---------------------------------------------------------------------------
  // Editing actions
  // ---------------------------------------------------------------------------

  void _addItem() => setState(() => _items.add(_LineFields()));

  void _removeItem(int index) {
    if (_items.length == 1) {
      setState(() {
        _items.first.dispose();
        _items.clear();
        _items.add(_LineFields());
      });
      return;
    }
    setState(() {
      _items[index].dispose();
      _items.removeAt(index);
    });
  }

  void _addTerm() => setState(() => _terms.add(TextEditingController()));

  void _removeTerm(int index) {
    if (_terms.length == 1) {
      setState(() {
        _terms.first.text = '';
      });
      return;
    }
    setState(() {
      _terms[index].dispose();
      _terms.removeAt(index);
    });
  }

  void _addDefaultTerms() {
    setState(() {
      for (final term in kDefaultTerms) {
        _terms.add(TextEditingController(text: term));
      }
      _terms.removeWhere((c) => c.text.trim().isEmpty);
      if (_terms.isEmpty) _terms.add(TextEditingController());
    });
  }

  /// Fills the lines from the selected design: panels, inverter and labour.
  void _fillFromDesign(Design design) {
    final panels = ref.read(panelsListProvider).valueOrNull ?? <Component>[];
    final inverters =
        ref.read(invertersListProvider).valueOrNull ?? <Component>[];

    final panel = panels
        .cast<Component?>()
        .firstWhere((c) => c?.id == design.panelId, orElse: () => null);
    final inverter = inverters
        .cast<Component?>()
        .firstWhere((c) => c?.id == design.inverterId, orElse: () => null);
    final settings = ref.read(settingsProvider).valueOrNull;

    for (final line in _items) {
      line.dispose();
    }
    _items.clear();

    if (panel != null) {
      final panelPrice = (panel.pricePerWatt ?? 0) * (panel.powerW ?? 0);
      _items.add(
        _LineFields(
          description: 'ألواح شمسية ${panel.brand} ${panel.model}'
              ' ${panel.powerW ?? 0} واط',
          quantity: design.panelCount <= 0 ? '1' : design.panelCount.toString(),
          unitPrice: panelPrice > 0 ? _trimNumber(panelPrice) : '',
          unit: 'لوح',
          warranty: '10 سنوات',
        ),
      );
    }

    if (inverter != null) {
      _items.add(
        _LineFields(
          description: 'إنفرتر ${inverter.brand} ${inverter.model}'
              ' ${inverter.powerKw ?? 0} ك.و',
          quantity: '1',
          unitPrice: inverter.price > 0 ? _trimNumber(inverter.price) : '',
          unit: 'جهاز',
          warranty: '5 سنوات',
        ),
      );
    }

    final labourPerKw = settings?.defaultPricePerKw ?? 0;
    if (labourPerKw > 0) {
      _items.add(
        _LineFields(
          description: 'أعمال التركيب والتوصيل والتشغيل',
          quantity: '1',
          unitPrice: _trimNumber(labourPerKw * design.capacityKw),
          unit: 'خدمة',
        ),
      );
    }

    if (_items.isEmpty) _items.add(_LineFields());
    setState(() {});
  }

  Future<void> _save() async {
    if (!_formKey.currentState!.validate()) return;

    final customerId = _selectedCustomerId;
    final designId = _selectedDesignId;
    if (customerId == null) {
      _showMessage('اختر العميل أولاً');
      return;
    }
    if (designId == null) {
      _showMessage('اختر التصميم المرتبط بعرض السعر');
      return;
    }

    final items = _currentItems;
    if (items.isEmpty) {
      _showMessage('أضف صنفاً واحداً على الأقل');
      return;
    }

    final terms = _terms
        .map((c) => c.text.trim())
        .where((t) => t.isNotEmpty)
        .toList()
        .asMap()
        .entries
        .map((entry) => Term.create(
              quoteId: 0,
              text: entry.value,
              orderIndex: entry.key,
            ))
        .toList();

    setState(() => _saving = true);
    try {
      final base = widget.quote ??
          Quote.create(
            designId: designId,
            customerId: customerId,
          );
      final quote = base.copyWith(
        designId: designId,
        customerId: customerId,
        discount: double.tryParse(_discountController.text.trim()) ?? 0,
        tax: double.tryParse(_taxController.text.trim()) ?? 0,
        status: _selectedStatus,
      );

      await ref.read(quotesListProvider.notifier).saveQuote(
            quote: quote,
            items: items,
            terms: terms,
          );

      if (mounted) Navigator.of(context).pop(true);
    } catch (error) {
      if (mounted) {
        setState(() => _saving = false);
        _showMessage('تعذر حفظ عرض السعر: $error');
      }
    }
  }

  void _showMessage(String message) {
    ScaffoldMessenger.of(context)
      ..clearSnackBars()
      ..showSnackBar(SnackBar(content: Text(message)));
  }

  // ---------------------------------------------------------------------------
  // UI
  // ---------------------------------------------------------------------------

  @override
  Widget build(BuildContext context) {
    final customersAsync = ref.watch(customersForDropdownProvider);
    final designsAsync = _selectedCustomerId == null
        ? const AsyncValue<List<Design>>.loading()
        : ref.watch(designsForCustomerProvider(_selectedCustomerId!));

    return Scaffold(
      appBar: AppBar(
        title: Text(_isEditing ? 'تعديل عرض السعر' : 'عرض سعر جديد'),
        actions: [
          TextButton.icon(
            onPressed: _saving ? null : _save,
            icon: _saving
                ? const SizedBox(
                    width: 16,
                    height: 16,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  )
                : const Icon(Icons.save),
            label: const Text('حفظ'),
          ),
        ],
      ),
      body: Form(
        key: _formKey,
        child: ListView(
          padding: const EdgeInsets.fromLTRB(16, 12, 16, 120),
          children: [
            _sectionTitle(context, 'العميل والتصميم'),
            customersAsync.when(
              loading: () => const LinearProgressIndicator(),
              error: (error, _) => Text('خطأ في تحميل العملاء: $error'),
              data: (customers) {
                if (customers.isEmpty) {
                  return const Padding(
                    padding: EdgeInsets.symmetric(vertical: 8),
                    child: Text('أضف عميلاً أولاً قبل إنشاء عرض سعر.'),
                  );
                }
                return DropdownButtonFormField<int>(
                  initialValue: _visibleId(
                    customers.map((c) => c.id),
                    _selectedCustomerId,
                  ),
                  decoration: const InputDecoration(
                    labelText: 'العميل',
                    prefixIcon: Icon(Icons.person),
                    border: OutlineInputBorder(),
                  ),
                  items: [
                    for (final customer in customers)
                      DropdownMenuItem<int>(
                        value: customer.id,
                        child: Text(customer.name),
                      ),
                  ],
                  onChanged: (value) => setState(() {
                    _selectedCustomerId = value;
                    _selectedDesignId = null;
                  }),
                  validator: (value) =>
                      value == null ? 'اختر العميل' : null,
                );
              },
            ),
            const SizedBox(height: 12),
            designsAsync.when(
              loading: () => const LinearProgressIndicator(),
              error: (error, _) => Text('خطأ في تحميل التصميمات: $error'),
              data: (designs) {
                if (designs.isEmpty) {
                  return const Padding(
                    padding: EdgeInsets.symmetric(vertical: 8),
                    child: Text('لا توجد تصميمات لهذا العميل.'),
                  );
                }
                return Column(
                  children: [
                    DropdownButtonFormField<int>(
                      initialValue: _visibleId(
                        designs.map((d) => d.id),
                        _selectedDesignId,
                      ),
                      decoration: const InputDecoration(
                        labelText: 'التصميم',
                        prefixIcon: Icon(Icons.design_services),
                        border: OutlineInputBorder(),
                      ),
                      items: [
                        for (final design in designs)
                          DropdownMenuItem<int>(
                            value: design.id,
                            child: Text(
                              '${design.capacityKw} ك.و · ${design.panelCount} لوح · ${_formatDate(design.createdAt)}',
                            ),
                          ),
                      ],
                      onChanged: (value) =>
                          setState(() => _selectedDesignId = value),
                      validator: (value) => value == null ? 'اختر التصميم' : null,
                    ),
                    const SizedBox(height: 8),
                    Align(
                      alignment: AlignmentDirectional.centerStart,
                      child: OutlinedButton.icon(
                        icon: const Icon(Icons.auto_fix_high),
                        label: const Text('تعبئة الأصناف من التصميم'),
                        onPressed: () {
                          final design = designs.firstWhere(
                            (d) => d.id == _selectedDesignId,
                            orElse: () => designs.first,
                          );
                          _fillFromDesign(design);
                        },
                      ),
                    ),
                  ],
                );
              },
            ),
            const SizedBox(height: 20),
            _sectionTitle(context, 'الأصناف'),
            for (var i = 0; i < _items.length; i++) _buildItemCard(i),
            const SizedBox(height: 8),
            OutlinedButton.icon(
              onPressed: _addItem,
              icon: const Icon(Icons.add),
              label: const Text('إضافة صنف'),
            ),
            const SizedBox(height: 20),
            _sectionTitle(context, 'الشروط'),
            for (var i = 0; i < _terms.length; i++) _buildTermRow(i),
            const SizedBox(height: 8),
            Row(
              children: [
                OutlinedButton.icon(
                  onPressed: _addTerm,
                  icon: const Icon(Icons.add),
                  label: const Text('شرط'),
                ),
                const SizedBox(width: 8),
                TextButton.icon(
                  onPressed: _addDefaultTerms,
                  icon: const Icon(Icons.playlist_add),
                  label: const Text('الشروط الافتراضية'),
                ),
              ],
            ),
            const SizedBox(height: 20),
            _sectionTitle(context, 'الخصم والضريبة والحالة'),
            Row(
              children: [
                Expanded(
                  child: TextFormField(
                    controller: _discountController,
                    keyboardType:
                        const TextInputType.numberWithOptions(decimal: true),
                    decoration: const InputDecoration(
                      labelText: 'الخصم %',
                      prefixIcon: Icon(Icons.discount),
                      border: OutlineInputBorder(),
                    ),
                    onChanged: (_) => setState(() {}),
                    validator: _validatePercent,
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: TextFormField(
                    controller: _taxController,
                    keyboardType:
                        const TextInputType.numberWithOptions(decimal: true),
                    decoration: const InputDecoration(
                      labelText: 'الضريبة %',
                      prefixIcon: Icon(Icons.receipt_long),
                      border: OutlineInputBorder(),
                    ),
                    onChanged: (_) => setState(() {}),
                    validator: _validatePercent,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 12),
            DropdownButtonFormField<String>(
              initialValue: _selectedStatus,
              decoration: const InputDecoration(
                labelText: 'الحالة',
                prefixIcon: Icon(Icons.flag),
                border: OutlineInputBorder(),
              ),
              items: [
                for (final status in QuoteStatus.values)
                  DropdownMenuItem<String>(
                    value: status.value,
                    child: Text(status.labelAr),
                  ),
              ],
              onChanged: (value) =>
                  setState(() => _selectedStatus = value ?? _selectedStatus),
            ),
            const SizedBox(height: 20),
            _buildTotalsCard(),
          ],
        ),
      ),
      bottomNavigationBar: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(12),
          child: FilledButton.icon(
            onPressed: _saving ? null : _save,
            icon: const Icon(Icons.save),
            label: Text(_isEditing ? 'حفظ التعديلات' : 'إنشاء عرض السعر'),
          ),
        ),
      ),
    );
  }

  Widget _sectionTitle(BuildContext context, String title) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Text(
        title,
        style: Theme.of(context).textTheme.titleMedium?.copyWith(
              fontWeight: FontWeight.bold,
              color: Theme.of(context).colorScheme.primary,
            ),
      ),
    );
  }

  Widget _buildItemCard(int index) {
    final line = _items[index];
    return Card(
      margin: const EdgeInsets.only(bottom: 12),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          children: [
            Row(
              children: [
                Expanded(
                  child: Text(
                    'الصنف ${index + 1}',
                    style: const TextStyle(fontWeight: FontWeight.bold),
                  ),
                ),
                IconButton(
                  icon: const Icon(Icons.delete_outline, color: Colors.red),
                  tooltip: 'حذف الصنف',
                  onPressed: () => _removeItem(index),
                ),
              ],
            ),
            TextFormField(
              controller: line.descriptionController,
              decoration: const InputDecoration(
                labelText: 'البيان',
                border: OutlineInputBorder(),
                isDense: true,
              ),
              onChanged: (_) => setState(() {}),
              validator: (value) {
                if (index != 0 && (value == null || value.trim().isEmpty)) {
                  return null; // empty extra rows are ignored
                }
                if (value == null || value.trim().isEmpty) {
                  return 'أدخل البيان';
                }
                return null;
              },
            ),
            const SizedBox(height: 8),
            Row(
              children: [
                Expanded(
                  flex: 2,
                  child: TextFormField(
                    controller: line.quantityController,
                    keyboardType: TextInputType.number,
                    decoration: const InputDecoration(
                      labelText: 'الكمية',
                      border: OutlineInputBorder(),
                      isDense: true,
                    ),
                    onChanged: (_) => setState(() {}),
                    validator: (value) {
                      if ((value == null || value.trim().isEmpty)) return null;
                      final parsed = int.tryParse(value.trim());
                      if (parsed == null || parsed <= 0) return 'كمية غير صحيحة';
                      return null;
                    },
                  ),
                ),
                const SizedBox(width: 8),
                Expanded(
                  flex: 3,
                  child: DropdownButtonFormField<String>(
                    initialValue:
                        kQuoteUnits.contains(line.unit) ? line.unit : 'وحدة',
                    decoration: const InputDecoration(
                      labelText: 'الوحدة',
                      border: OutlineInputBorder(),
                      isDense: true,
                    ),
                    items: [
                      for (final unit in kQuoteUnits)
                        DropdownMenuItem<String>(
                          value: unit,
                          child: Text(unit),
                        ),
                    ],
                    onChanged: (value) =>
                        setState(() => line.unit = value ?? line.unit),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 8),
            TextFormField(
              controller: line.unitPriceController,
              keyboardType:
                  const TextInputType.numberWithOptions(decimal: true),
              decoration: const InputDecoration(
                labelText: 'سعر الوحدة (ج.م)',
                border: OutlineInputBorder(),
                isDense: true,
              ),
              onChanged: (_) => setState(() {}),
              validator: (value) {
                if (value == null || value.trim().isEmpty) return null;
                final parsed = double.tryParse(value.trim());
                if (parsed == null || parsed < 0) return 'سعر غير صحيح';
                return null;
              },
            ),
            const SizedBox(height: 8),
            Row(
              children: [
                Expanded(
                  child: TextFormField(
                    controller: line.originController,
                    decoration: const InputDecoration(
                      labelText: 'بلد المنشأ',
                      border: OutlineInputBorder(),
                      isDense: true,
                    ),
                  ),
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: TextFormField(
                    controller: line.warrantyController,
                    decoration: const InputDecoration(
                      labelText: 'الضمان',
                      border: OutlineInputBorder(),
                      isDense: true,
                    ),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 6),
            Align(
              alignment: AlignmentDirectional.centerStart,
              child: Text(
                'الإجمالي: ${CurrencyFormatter.money(_lineTotal(line))}',
                style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                      fontWeight: FontWeight.bold,
                      color: Theme.of(context).colorScheme.primary,
                    ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildTermRow(int index) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Row(
        children: [
          Expanded(
            child: TextFormField(
              controller: _terms[index],
              decoration: InputDecoration(
                labelText: 'الشرط ${index + 1}',
                border: const OutlineInputBorder(),
                isDense: true,
              ),
            ),
          ),
          IconButton(
            icon: const Icon(Icons.remove_circle_outline, color: Colors.red),
            tooltip: 'حذف الشرط',
            onPressed: () => _removeTerm(index),
          ),
        ],
      ),
    );
  }

  Widget _buildTotalsCard() {
    final totals = _totals;
    return Card(
      color: Theme.of(context).colorScheme.surfaceContainerHighest,
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          children: [
            _totalRow('المجموع الفرعي', CurrencyFormatter.money(totals.subtotal)),
            if (totals.discountPercent > 0)
              _totalRow(
                'الخصم (${_trimNumber(totals.discountPercent)}%)',
                '- ${CurrencyFormatter.money(totals.discountAmount)}',
              ),
            if (totals.taxPercent > 0)
              _totalRow(
                'الضريبة (${_trimNumber(totals.taxPercent)}%)',
                CurrencyFormatter.money(totals.taxAmount),
              ),
            const Divider(),
            _totalRow(
              'الإجمالي',
              CurrencyFormatter.money(totals.total),
              bold: true,
            ),
          ],
        ),
      ),
    );
  }

  Widget _totalRow(String label, String value, {bool bold = false}) {
    final style = Theme.of(context).textTheme.bodyMedium?.copyWith(
          fontWeight: bold ? FontWeight.bold : FontWeight.normal,
        );
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 3),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Text(value, style: style),
          Text(label, style: style),
        ],
      ),
    );
  }

  double _lineTotal(_LineFields line) {
    final quantity = int.tryParse(line.quantityController.text.trim()) ?? 0;
    final price = double.tryParse(line.unitPriceController.text.trim()) ?? 0;
    return quantity * price;
  }

  String? _validatePercent(String? value) {
    if (value == null || value.trim().isEmpty) return null;
    final parsed = double.tryParse(value.trim());
    if (parsed == null) return 'قيمة غير صحيحة';
    if (parsed < 0 || parsed > 100) return 'أدخل قيمة من 0 إلى 100';
    return null;
  }

  /// `DropdownButtonFormField` throws when its value is not part of `items`,
  /// so an unknown id (a deleted customer/design) is mapped back to `null`.
  static int? _visibleId(Iterable<int?> ids, int? id) {
    if (id == null) return null;
    for (final value in ids) {
      if (value == id) return id;
    }
    return null;
  }

  static String _trimNumber(double value) {
    if (value == value.roundToDouble()) return value.toStringAsFixed(0);
    return value.toStringAsFixed(2);
  }

  static String _formatDate(DateTime date) {
    final local = date.toLocal();
    return '${local.year}/${local.month.toString().padLeft(2, '0')}/${local.day.toString().padLeft(2, '0')}';
  }
}
