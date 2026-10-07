import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../data/models/design.dart';
import '../../data/models/component.dart';
import '../providers/design_providers.dart';
import '../providers/component_providers.dart';
import '../../../../core/utils/solar_calculator.dart';

class DesignFormScreen extends ConsumerStatefulWidget {
  final Design? design;

  const DesignFormScreen({super.key, this.design});

  @override
  ConsumerState<DesignFormScreen> createState() => _DesignFormScreenState();
}

class _DesignFormScreenState extends ConsumerState<DesignFormScreen> {
  final _formKey = GlobalKey<FormState>();

  final _capacityController = TextEditingController();
  final _notesController = TextEditingController();

  int? _selectedCustomerId;
  String _selectedSystemType = 'on_grid';
  String _selectedCustomerType = 'residential';
  int? _selectedInverterId;
  int? _selectedPanelId;

  int _manualPanelCount = 0;
  int _manualStringCount = 0;
  bool _isManualOverride = false;

  int _totalPanels = 0;
  int _maxPanelsPerString = 0;
  int _numberOfStrings = 0;
  List<int> _distribution = [];

  double _panelPricePerWatt = 0;
  double _panelPowerW = 0;
  double _inverterPrice = 0;

  bool get _isEditing => widget.design != null;

  @override
  void initState() {
    super.initState();
    if (_isEditing) {
      final d = widget.design!;
      _selectedCustomerId = d.customerId;
      _capacityController.text = d.capacityKw.toString();
      _selectedSystemType = d.systemType;
      _selectedCustomerType = d.customerType;
      _selectedInverterId = d.inverterId;
      _selectedPanelId = d.panelId;
      _notesController.text = d.notes ?? '';
      _manualPanelCount = d.panelCount;
      _manualStringCount = d.stringCount;
      _isManualOverride = d.panelCount > 0 && d.stringCount > 0;
    }
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) _calculate();
    });
  }

  @override
  void dispose() {
    _capacityController.dispose();
    _notesController.dispose();
    super.dispose();
  }

  void _calculate() {
    if (!mounted) return;
    final capacityKw = double.tryParse(_capacityController.text) ?? 0;
    final panelsAsync = ref.read(panelsListProvider);
    final invertersAsync = ref.read(invertersListProvider);
    final panels = panelsAsync.valueOrNull;
    final inverters = invertersAsync.valueOrNull;
    if (panels == null || inverters == null) return;

    final panel = panels.firstWhere(
      (p) => p.id == _selectedPanelId,
      orElse: () => Component(type: 'panel', brand: '', model: '', createdAt: DateTime.now()),
    );
    final inverter = inverters.firstWhere(
      (inv) => inv.id == _selectedInverterId,
      orElse: () => Component(type: 'inverter', brand: '', model: '', createdAt: DateTime.now()),
    );

    int nextTotalPanels = _totalPanels;
    int nextMaxPanelsPerString = _maxPanelsPerString;
    int nextNumberOfStrings = _numberOfStrings;
    List<int> nextDistribution = _distribution;
    double nextPanelPowerW = _panelPowerW;
    double nextPanelPricePerWatt = _panelPricePerWatt;
    double nextInverterPrice = _inverterPrice;

    if (panel.powerW != null && panel.vocV != null) {
      nextPanelPowerW = panel.powerW!.toDouble();
      nextPanelPricePerWatt = panel.pricePerWatt ?? 0;
      if (inverter.maxDcVoltage != null) {
        final capacityW = capacityKw * 1000;
        nextTotalPanels = SolarCalculator.calculateTotalPanels(capacityW, nextPanelPowerW);
        nextMaxPanelsPerString = SolarCalculator.calculateMaxPanelsPerString(inverter.maxDcVoltage!, panel.vocV!);
        nextNumberOfStrings = SolarCalculator.calculateNumberOfStrings(nextTotalPanels, nextMaxPanelsPerString);
        nextDistribution = SolarCalculator.distributePanelsInStrings(nextTotalPanels, nextNumberOfStrings);
      }
    }
    if (inverter.maxDcVoltage != null) {
      nextInverterPrice = inverter.price;
    }

    final distributionChanged = nextDistribution.length != _distribution.length ||
        !List.generate(nextDistribution.length, (i) => nextDistribution[i] == _distribution[i]).every((e) => e);

    if (nextTotalPanels != _totalPanels ||
        nextMaxPanelsPerString != _maxPanelsPerString ||
        nextNumberOfStrings != _numberOfStrings ||
        distributionChanged ||
        nextPanelPowerW != _panelPowerW ||
        nextPanelPricePerWatt != _panelPricePerWatt ||
        nextInverterPrice != _inverterPrice) {
      setState(() {
        _totalPanels = nextTotalPanels;
        _maxPanelsPerString = nextMaxPanelsPerString;
        _numberOfStrings = nextNumberOfStrings;
        _distribution = nextDistribution;
        _panelPowerW = nextPanelPowerW;
        _panelPricePerWatt = nextPanelPricePerWatt;
        _inverterPrice = nextInverterPrice;
      });
    }
  }

  void _resetToAuto() {
    setState(() {
      _isManualOverride = false;
      _manualPanelCount = 0;
      _manualStringCount = 0;
    });
    _calculate();
  }

  Future<void> _save() async {
    if (!_formKey.currentState!.validate()) return;
    if (_selectedCustomerId == null) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('الرجاء اختيار العميل')));
      return;
    }
    if (_selectedPanelId == null) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('الرجاء اختيار اللوح الشمسي')));
      return;
    }
    if (_selectedInverterId == null) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('الرجاء اختيار الإنفرتر')));
      return;
    }

    _calculate();

    final capacityKw = double.tryParse(_capacityController.text) ?? 0;
    int panelCount, stringCount, panelsPerString;
    if (_isManualOverride) {
      panelCount = _manualPanelCount;
      stringCount = _manualStringCount;
      panelsPerString = stringCount > 0 ? (panelCount ~/ stringCount) : 0;
    } else {
      panelCount = _totalPanels;
      stringCount = _numberOfStrings;
      panelsPerString = _maxPanelsPerString;
    }

    final design = Design(
      id: widget.design?.id,
      customerId: _selectedCustomerId!,
      capacityKw: capacityKw,
      systemType: _selectedSystemType,
      customerType: _selectedCustomerType,
      inverterId: _selectedInverterId,
      panelId: _selectedPanelId,
      panelCount: panelCount,
      stringCount: stringCount,
      panelsPerString: panelsPerString,
      notes: _notesController.text.trim().isEmpty ? null : _notesController.text.trim(),
      createdAt: widget.design?.createdAt ?? DateTime.now(),
    );

    try {
      final notifier = ref.read(designsListProvider.notifier);
      final int? result;
      if (_isEditing) {
        result = await notifier.updateDesign(design);
      } else {
        result = await notifier.add(design);
      }

      if (result == null || result <= 0) {
        if (mounted) {
           ScaffoldMessenger.of(context).showSnackBar(
             const SnackBar(content: Text('فشل الحفظ: لم يتم حفظ التصميم')),
           );
        }
        return;
      }

      if (mounted) Navigator.of(context).pop();
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('فشل الحفظ: $e')),
        );
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    ref.listen<AsyncValue<List<Component>>>(panelsListProvider, (_, _) => _calculate());
    ref.listen<AsyncValue<List<Component>>>(invertersListProvider, (_, _) => _calculate());

    return Scaffold(
      appBar: AppBar(
        title: Text(_isEditing ? 'تعديل التصميم' : 'تصميم جديد'),
        leading: IconButton(icon: const Icon(Icons.arrow_back), onPressed: () => Navigator.of(context).pop()),
      ),
      body: Form(
        key: _formKey,
        child: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            _SectionHeader(label: 'المعلومات الأساسية'),
            const SizedBox(height: 12),
            Consumer(builder: (context, ref, _) {
              final customersAsync = ref.watch(customersForDropdownProvider);
              return customersAsync.when(
                loading: () => const LinearProgressIndicator(),
                error: (_, e) => Text('خطأ: $e'),
                data: (customers) => DropdownButtonFormField<int>(
                  decoration: const InputDecoration(labelText: 'العميل *', prefixIcon: Icon(Icons.person)),
                  initialValue: customers.any((c) => c.id == _selectedCustomerId) ? _selectedCustomerId : null,
                  items: customers.map((c) => DropdownMenuItem(value: c.id, child: Text(c.name))).toList(),
                  onChanged: (v) => setState(() => _selectedCustomerId = v),
                  validator: (v) => v == null ? 'الرجاء اختيار عميل' : null,
                ),
              );
            }),
            const SizedBox(height: 12),
            TextFormField(
              controller: _capacityController,
              decoration: const InputDecoration(labelText: 'السعة (ك.و) *', prefixIcon: Icon(Icons.bolt), suffixText: 'ك.و'),
              keyboardType: const TextInputType.numberWithOptions(decimal: true),
              validator: (v) { if (v == null || v.isEmpty) return 'مطلوب'; if (double.tryParse(v) == null) return 'أدخل رقماً'; return null; },
              onChanged: (_) => _calculate(),
            ),
            const SizedBox(height: 12),
            DropdownButtonFormField<String>(
              decoration: const InputDecoration(labelText: 'نوع النظام', prefixIcon: Icon(Icons.grid_on)),
              initialValue: _selectedSystemType,
              items: const [
                DropdownMenuItem(value: 'on_grid', child: Text('شبكي (On-Grid)')),
                DropdownMenuItem(value: 'off_grid', child: Text('غير شبكي (Off-Grid)')),
                DropdownMenuItem(value: 'hybrid', child: Text('هجين (Hybrid)')),
              ],
              onChanged: (v) => setState(() => _selectedSystemType = v!),
            ),
            const SizedBox(height: 12),
            DropdownButtonFormField<String>(
              decoration: const InputDecoration(labelText: 'نوع العميل', prefixIcon: Icon(Icons.business)),
              initialValue: _selectedCustomerType,
              items: const [
                DropdownMenuItem(value: 'residential', child: Text('سكني')),
                DropdownMenuItem(value: 'commercial', child: Text('تجاري')),
                DropdownMenuItem(value: 'industrial', child: Text('صناعي')),
                DropdownMenuItem(value: 'agricultural', child: Text('زراعي')),
              ],
              onChanged: (v) => setState(() => _selectedCustomerType = v!),
            ),
            const SizedBox(height: 24),
            _SectionHeader(label: 'المكونات'),
            const SizedBox(height: 12),
            Consumer(builder: (context, ref, _) {
              final invertersAsync = ref.watch(invertersListProvider);
              return invertersAsync.when(
                loading: () => const LinearProgressIndicator(),
                error: (_, e) => Text('خطأ: $e'),
                data: (inverters) => DropdownButtonFormField<int>(
                  decoration: const InputDecoration(labelText: 'الإنفرتر *', prefixIcon: Icon(Icons.electrical_services)),
                  initialValue: inverters.any((inv) => inv.id == _selectedInverterId) ? _selectedInverterId : null,
                  items: inverters.map((inv) => DropdownMenuItem(value: inv.id, child: Text('${inv.brand} ${inv.model}'))).toList(),
                  onChanged: (v) {
                    setState(() => _selectedInverterId = v);
                    _calculate();
                  },
                  validator: (v) => v == null ? 'الرجاء اختيار إنفرتر' : null,
                ),
              );
            }),
            const SizedBox(height: 12),
            Consumer(builder: (context, ref, _) {
              final panelsAsync = ref.watch(panelsListProvider);
              return panelsAsync.when(
                loading: () => const LinearProgressIndicator(),
                error: (_, e) => Text('خطأ: $e'),
                data: (panels) => DropdownButtonFormField<int>(
                  decoration: const InputDecoration(labelText: 'اللوح الشمسي *', prefixIcon: Icon(Icons.solar_power)),
                  initialValue: panels.any((p) => p.id == _selectedPanelId) ? _selectedPanelId : null,
                  items: panels.map((p) => DropdownMenuItem(value: p.id, child: Text('${p.brand} ${p.model} (${p.powerW} W)'))).toList(),
                  onChanged: (v) {
                    setState(() => _selectedPanelId = v);
                    _calculate();
                  },
                  validator: (v) => v == null ? 'الرجاء اختيار لوح شمسي' : null,
                ),
              );
            }),
            const SizedBox(height: 24),
            _SectionHeader(label: 'الحسابات التلقائية'),
            const SizedBox(height: 12),
            Card(
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: Column(
                  children: [
                    _InfoRow(label: 'إجمالي الألواح', value: '$_totalPanels لوح'),
                    const Divider(height: 24),
                    _InfoRow(label: 'أقصى عدد في السلسلة', value: '$_maxPanelsPerString لوح'),
                    const Divider(height: 24),
                    _InfoRow(label: 'عدد السلاسل', value: '$_numberOfStrings سلسلة'),
                    const Divider(height: 24),
                    if (_distribution.isNotEmpty) ...[
                      Text('توزيع الألواح:', style: Theme.of(context).textTheme.bodySmall),
                      const SizedBox(height: 4),
                      ...List.generate(_distribution.length, (i) => Padding(
                        padding: const EdgeInsets.only(bottom: 2),
                        child: Text('السلسلة ${i + 1}: ${_distribution[i]} لوح', style: Theme.of(context).textTheme.bodySmall?.copyWith(fontFamily: 'monospace')),
                      )),
                    ],
                  ],
                ),
              ),
            ),
            const SizedBox(height: 24),
            _SectionHeader(label: 'التعديل اليدوي (اختياري)'),
            const SizedBox(height: 12),
            Card(
              color: _isManualOverride ? Colors.orange.shade50 : Theme.of(context).colorScheme.surface,
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: Column(
                  children: [
                    Row(
                      children: [
                        Expanded(
                          child: TextFormField(
                            initialValue: _manualPanelCount.toString(),
                            decoration: const InputDecoration(labelText: 'عدد الألواح', prefixIcon: Icon(Icons.format_list_numbered)),
                            keyboardType: TextInputType.number,
                            onChanged: (v) { final val = int.tryParse(v); if (val != null) setState(() { _manualPanelCount = val; _isManualOverride = true; }); },
                          ),
                        ),
                        const SizedBox(width: 12),
                        Expanded(
                          child: TextFormField(
                            initialValue: _manualStringCount.toString(),
                            decoration: const InputDecoration(labelText: 'عدد السلاسل', prefixIcon: Icon(Icons.call_merge)),
                            keyboardType: TextInputType.number,
                            onChanged: (v) { final val = int.tryParse(v); if (val != null) setState(() { _manualStringCount = val; _isManualOverride = true; }); },
                          ),
                        ),
                      ],
                    ),
                    if (_isManualOverride) ...[
                      const SizedBox(height: 8),
                      Row(
                        children: [
                          Text('تم التعديل يدوياً', style: Theme.of(context).textTheme.bodySmall?.copyWith(color: Colors.orange.shade700, fontWeight: FontWeight.bold)),
                          const Spacer(),
                          TextButton(onPressed: _resetToAuto, child: const Text('إعادة حساب تلقائي')),
                        ],
                      ),
                    ],
                  ],
                ),
              ),
            ),
            const SizedBox(height: 24),
            _SectionHeader(label: 'الملخص المالي'),
            const SizedBox(height: 12),
            Card(
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: Column(
                  children: [
                    _InfoRow(label: 'تكلفة الألواح', value: '($_totalPanels × ${_panelPowerW.toInt()} × ${_panelPricePerWatt.toStringAsFixed(2)})'),
                    const Divider(height: 24),
                    _InfoRow(label: 'تكلفة الإنفرتر', value: '${_inverterPrice.toStringAsFixed(0)} ج.م'),
                    const Divider(height: 24),
                    _MoneyRow(label: 'إجمالي تكلفة المكونات', value: '${(_totalPanels * _panelPowerW * _panelPricePerWatt + _inverterPrice).toStringAsFixed(2)} ج.م'),
                  ],
                ),
              ),
            ),
            const SizedBox(height: 24),
            TextFormField(
              controller: _notesController,
              decoration: const InputDecoration(labelText: 'ملاحظات', prefixIcon: Icon(Icons.note), alignLabelWithHint: true),
              maxLines: 3,
            ),
            const SizedBox(height: 32),
            FilledButton(onPressed: () => _save(), child: Text(_isEditing ? 'تحديث' : 'حفظ التصميم')),
            const SizedBox(height: 16),
          ],
        ),
      ),
    );
  }
}

class _SectionHeader extends StatelessWidget {
  final String label;
  const _SectionHeader({required this.label});
  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Expanded(child: Divider(color: Theme.of(context).colorScheme.outlineVariant)),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 12),
          child: Text(label, style: Theme.of(context).textTheme.labelLarge?.copyWith(color: Theme.of(context).colorScheme.primary)),
        ),
        Expanded(child: Divider(color: Theme.of(context).colorScheme.outlineVariant)),
      ],
    );
  }
}

class _InfoRow extends StatelessWidget {
  final String label;
  final String value;
  const _InfoRow({required this.label, required this.value});
  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisAlignment: MainAxisAlignment.spaceBetween,
      children: [
        Text(label, style: Theme.of(context).textTheme.bodyMedium),
        Text(value, style: Theme.of(context).textTheme.bodyMedium?.copyWith(fontWeight: FontWeight.bold)),
      ],
    );
  }
}

class _MoneyRow extends StatelessWidget {
  final String label;
  final String value;
  const _MoneyRow({required this.label, required this.value});
  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisAlignment: MainAxisAlignment.spaceBetween,
      children: [
        Text(label, style: Theme.of(context).textTheme.titleMedium),
        Text(value, style: Theme.of(context).textTheme.titleMedium?.copyWith(color: Theme.of(context).colorScheme.primary, fontWeight: FontWeight.bold)),
      ],
    );
  }
}
