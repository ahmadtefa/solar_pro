import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../data/models/component.dart';
import '../providers/component_providers.dart';
import '../../../../core/utils/solar_calculator.dart';

class ComponentFormScreen extends ConsumerStatefulWidget {
  final Component? component;

  const ComponentFormScreen({super.key, this.component});

  @override
  ConsumerState<ComponentFormScreen> createState() =>
      _ComponentFormScreenState();
}

class _ComponentFormScreenState extends ConsumerState<ComponentFormScreen> {
  final _formKey = GlobalKey<FormState>();

  // Shared controllers
  final _brandController = TextEditingController();
  final _modelController = TextEditingController();

  // Panel-only controllers
  final _pricePerWattController = TextEditingController();
  final _powerWController = TextEditingController();
  final _vocVController = TextEditingController();

  // Inverter-only controllers
  final _priceController = TextEditingController();
  final _powerKwController = TextEditingController();
  final _powerHpController = TextEditingController();
  final _maxDcVoltageController = TextEditingController();

  late String _selectedType;
  bool _isLoading = false;

  // Prevent recursive calls when auto-converting kW ↔ HP
  bool _convertingPower = false;

  bool get _isEditing => widget.component != null;
  bool get _isPanel => _selectedType == ComponentType.panel.value;

  @override
  void initState() {
    super.initState();
    final c = widget.component;
    if (c != null) {
      _selectedType = c.type;
      _brandController.text = c.brand;
      _modelController.text = c.model;
      // Panel fields
      _pricePerWattController.text = c.pricePerWatt?.toString() ?? '';
      _powerWController.text = c.powerW?.toString() ?? '';
      _vocVController.text = c.vocV?.toString() ?? '';
      // Inverter fields
      _priceController.text = c.price > 0 ? c.price.toString() : '';
      _powerKwController.text = c.powerKw?.toString() ?? '';
      _powerHpController.text = c.powerHp?.toStringAsFixed(2) ?? '';
      _maxDcVoltageController.text = c.maxDcVoltage?.toString() ?? '';
    } else {
      _selectedType = ComponentType.panel.value;
    }

    // Wire up auto-conversion listeners
    _powerKwController.addListener(_onKwChanged);
    _powerHpController.addListener(_onHpChanged);
  }

  @override
  void dispose() {
    _brandController.dispose();
    _modelController.dispose();
    _pricePerWattController.dispose();
    _powerWController.dispose();
    _vocVController.dispose();
    _priceController.dispose();
    _powerKwController.dispose();
    _powerHpController.dispose();
    _maxDcVoltageController.dispose();
    super.dispose();
  }

  // ---------------------------------------------------------------------------
  // Auto-conversion kW ↔ HP
  // ---------------------------------------------------------------------------

  void _onKwChanged() {
    if (_convertingPower) return;
    final kw = double.tryParse(_powerKwController.text);
    if (kw == null) return;
    _convertingPower = true;
    _powerHpController.text = SolarCalculator.kwToHp(kw).toStringAsFixed(2);
    _convertingPower = false;
  }

  void _onHpChanged() {
    if (_convertingPower) return;
    final hp = double.tryParse(_powerHpController.text);
    if (hp == null) return;
    _convertingPower = true;
    _powerKwController.text = SolarCalculator.hpToKw(hp).toStringAsFixed(3);
    _convertingPower = false;
  }

  // ---------------------------------------------------------------------------
  // Validation helpers
  // ---------------------------------------------------------------------------

  String? _positiveNumber(String? value) {
    if (value == null || value.isEmpty) return 'هذا الحقل مطلوب';
    final number = double.tryParse(value);
    if (number == null) return 'أدخل رقماً';
    if (number <= 0) return ' يجب أن يكون أكبر من صفر';
    return null;
  }

  // ---------------------------------------------------------------------------
  // Save
  // ---------------------------------------------------------------------------

  Future<void> _save() async {
    if (!_formKey.currentState!.validate()) return;
    setState(() => _isLoading = true);

    try {
      final panelNotifier = ref.read(panelsListProvider.notifier);
      final inverterNotifier = ref.read(invertersListProvider.notifier);
      int? result;

      if (_isEditing) {
        final updated = widget.component!.copyWith(
          type: _selectedType,
          brand: _brandController.text.trim(),
          model: _modelController.text.trim(),
          pricePerWatt: _isPanel
              ? double.tryParse(_pricePerWattController.text)
              : widget.component!.pricePerWatt,
          price: _isPanel
              ? widget.component!.price
              : double.tryParse(_priceController.text) ?? 0,
          powerW: _isPanel ? int.tryParse(_powerWController.text) : null,
          vocV: _isPanel ? double.tryParse(_vocVController.text) : null,
          powerKw:
              !_isPanel ? double.tryParse(_powerKwController.text) : null,
          powerHp:
              !_isPanel ? double.tryParse(_powerHpController.text) : null,
          maxDcVoltage: !_isPanel
              ? double.tryParse(_maxDcVoltageController.text)
              : null,
        );
        if (_isPanel) {
          result = await panelNotifier.updateComponent(updated);
        } else {
          result = await inverterNotifier.updateComponent(updated);
        }
      } else {
        final newComponent = Component.create(
          type: _selectedType,
          brand: _brandController.text.trim(),
          model: _modelController.text.trim(),
          pricePerWatt: _isPanel
              ? double.tryParse(_pricePerWattController.text)
              : null,
          price: _isPanel ? 0 : (double.tryParse(_priceController.text) ?? 0),
          powerW: _isPanel ? int.tryParse(_powerWController.text) : null,
          vocV: _isPanel ? double.tryParse(_vocVController.text) : null,
          powerKw: !_isPanel ? double.tryParse(_powerKwController.text) : null,
          powerHp: !_isPanel ? double.tryParse(_powerHpController.text) : null,
          maxDcVoltage:
              !_isPanel ? double.tryParse(_maxDcVoltageController.text) : null,
        );
        if (_isPanel) {
          result = await panelNotifier.add(newComponent);
        } else {
          result = await inverterNotifier.add(newComponent);
        }
      }

      if (result == null || result <= 0) {
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(content: Text('فشل الحفظ: لم يتم حفظ المكوّن')),
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
    } finally {
      if (mounted) setState(() => _isLoading = false);
    }
  }

  // ---------------------------------------------------------------------------
  // Build
  // ---------------------------------------------------------------------------

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text(_isEditing ? 'تعديل المكوّن' : 'مكوّن جديد'),
        leading: IconButton(
          icon: const Icon(Icons.arrow_back),
          onPressed: _isLoading ? null : () => Navigator.of(context).pop(),
        ),
      ),
      body: Form(
        key: _formKey,
        child: ListView(
          padding: const EdgeInsets.all(20),
          children: [
            // ── Type selector ──────────────────────────────────────────────
            _SectionHeader(label: 'النوع'),
            const SizedBox(height: 12),
            SegmentedButton<String>(
              segments: [
                ButtonSegment(
                  value: ComponentType.panel.value,
                  label: Text('الألواح الشمسية'),
                  icon: Icon(Icons.solar_power),
                ),
                ButtonSegment(
                  value: ComponentType.inverter.value,
                  label: Text('الإنفرترات'),
                  icon: Icon(Icons.electrical_services),
                ),
              ],
              selected: {_selectedType},
              onSelectionChanged: (selected) {
                setState(() => _selectedType = selected.first);
              },
            ),

            const SizedBox(height: 24),

            // ── Common fields ──────────────────────────────────────────────
            _SectionHeader(label: 'المعلومات الأساسية'),
            const SizedBox(height: 12),
            TextFormField(
              controller: _brandController,
              decoration: const InputDecoration(
                labelText: 'العربية',
                prefixIcon: Icon(Icons.branding_watermark),
              ),
              validator: (value) => _requiredValidator(value),
            ),
            const SizedBox(height: 12),
            TextFormField(
              controller: _modelController,
              decoration: const InputDecoration(
                labelText: 'الموديل',
                prefixIcon: Icon(Icons.memory),
              ),
              validator: (value) => _requiredValidator(value),
            ),

            const SizedBox(height: 24),

            // ── Type-specific fields ───────────────────────────────────────
            if (_isPanel) ...[
              _SectionHeader(label: 'مواصفات اللوح الشمسي'),
              const SizedBox(height: 12),
              TextFormField(
                controller: _pricePerWattController,
                decoration: const InputDecoration(
                  labelText: 'سعر الواط (جنيه)',
                  prefixIcon: Icon(Icons.attach_money),
                  suffixText: 'ج.م/واط',
                ),
                keyboardType:
                    const TextInputType.numberWithOptions(decimal: true),
                validator: _positiveNumber,
              ),
              const SizedBox(height: 12),
              TextFormField(
                controller: _powerWController,
                decoration: const InputDecoration(
                  labelText: 'القدرة (واط)',
                  prefixIcon: Icon(Icons.bolt),
                  suffixText: 'W',
                ),
                keyboardType:
                    const TextInputType.numberWithOptions(decimal: true),
                validator: _positiveNumber,
              ),
              const SizedBox(height: 12),
              TextFormField(
                controller: _vocVController,
                decoration: const InputDecoration(
                  labelText: 'جهد الدائرة المفتوحة (Voc)',
                  prefixIcon: Icon(Icons.electric_bolt),
                  suffixText: 'V',
                ),
                keyboardType:
                    const TextInputType.numberWithOptions(decimal: true),
                validator: _positiveNumber,
              ),
            ] else ...[
              _SectionHeader(label: 'مواصفات الإنفرتر'),
              const SizedBox(height: 12),
              TextFormField(
                controller: _priceController,
                decoration: const InputDecoration(
                  labelText: 'السعر (جنيه)',
                  prefixIcon: Icon(Icons.attach_money),
                  suffixText: 'ج.م',
                ),
                keyboardType:
                    const TextInputType.numberWithOptions(decimal: true),
                validator: _positiveNumber,
              ),
              const SizedBox(height: 12),
              Row(
                children: [
                  Expanded(
                    child: TextFormField(
                      controller: _powerKwController,
                      decoration: const InputDecoration(
                        labelText: 'القدرة (kW)',
                        prefixIcon: Icon(Icons.speed),
                        suffixText: 'kW',
                      ),
                      keyboardType: const TextInputType.numberWithOptions(
                          decimal: true),
                      validator: _positiveNumber,
                    ),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: TextFormField(
                      controller: _powerHpController,
                      decoration: const InputDecoration(
                        labelText: 'القدرة (HP)',
                        prefixIcon: Icon(Icons.speed),
                        suffixText: 'HP',
                      ),
                      keyboardType: const TextInputType.numberWithOptions(
                          decimal: true),
                      validator: _positiveNumber,
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 8),
              Text(
                'يتم تحويل kW ↔ HP تلقائياً',
                style: Theme.of(context).textTheme.bodySmall
                    ?.copyWith(color: Theme.of(context).colorScheme.outline),
              ),
              const SizedBox(height: 16),
              TextFormField(
                controller: _maxDcVoltageController,
                decoration: const InputDecoration(
                  labelText: 'أقصى جهد DC',
                  prefixIcon: Icon(Icons.electric_bolt),
                  suffixText: 'V',
                ),
                keyboardType: const TextInputType.numberWithOptions(
                  decimal: true,
                ),
                validator: _positiveNumber,
              ),
            ],

            const SizedBox(height: 32),

            // ── Save button ─────────────────────────────────────────────────
            FilledButton(
              onPressed: _isLoading ? null : _save,
              style: FilledButton.styleFrom(
                minimumSize: const Size(double.infinity, 52),
              ),
              child: _isLoading
                  ? const SizedBox(
                      height: 22,
                      width: 22,
                      child: CircularProgressIndicator(
                        strokeWidth: 2,
                        color: Colors.white,
                      ),
                    )
                  : Text(_isEditing ? 'تحديث' : 'حفظ المكوّن'),
            ),

            const SizedBox(height: 16),
          ],
        ),
      ),
    );
  }

  String? _requiredValidator(String? value) {
    if (value == null || value.isEmpty) return 'هذا الحقل مطلوب';
    return null;
  }
}

// ---------------------------------------------------------------------------
// Small section header widget
// ---------------------------------------------------------------------------

class _SectionHeader extends StatelessWidget {
  final String label;
  const _SectionHeader({required this.label});

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Expanded(
          child: Divider(color: Theme.of(context).colorScheme.outlineVariant),
        ),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 12),
          child: Text(
            label,
            style: Theme.of(context).textTheme.labelLarge
                ?.copyWith(color: Theme.of(context).colorScheme.primary),
          ),
        ),
        Expanded(
          child: Divider(color: Theme.of(context).colorScheme.outlineVariant),
        ),
      ],
    );
  }
}
