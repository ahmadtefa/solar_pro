import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:geolocator/geolocator.dart';

import '../providers/customer_providers.dart';
import '../../../../core/constants/egypt_governorates.dart';
import '../../../customers/data/models/customer.dart';

class CustomerFormScreen extends ConsumerStatefulWidget {
  final Customer? customer;

  const CustomerFormScreen({super.key, this.customer});

  @override
  ConsumerState<CustomerFormScreen> createState() => _CustomerFormScreenState();
}

class _CustomerFormScreenState extends ConsumerState<CustomerFormScreen> {
  final _formKey = GlobalKey<FormState>();
  final _nameController = TextEditingController();
  final _phoneController = TextEditingController();
  final _addressController = TextEditingController();
  final _latController = TextEditingController();
  final _longController = TextEditingController();

  String _locationMethod = 'manual';
  EgyptGovernorate? _selectedGovernorate;
  bool _useMyLocation = false;
  bool _isLoading = false;

  bool get _isEditing => widget.customer != null;

  @override
  void initState() {
    super.initState();
    if (_isEditing) {
      final c = widget.customer!;
      _nameController.text = c.name;
      _phoneController.text = c.phone ?? '';
      _addressController.text = c.address ?? '';
      _latController.text = c.latitude?.toString() ?? '';
      _longController.text = c.longitude?.toString() ?? '';
      _locationMethod = c.locationMethod;
      // Only set governorate when governorateId is present
      if (c.governorateId != null) {
        _selectedGovernorate = egyptGovernorates.firstWhere(
          (g) => g.id == c.governorateId,
          orElse: () => egyptGovernorates.first,
        );
      }
      // Show coordinate fields if customer already has GPS data
      if (c.latitude != null || c.longitude != null) {
        _useMyLocation = true;
      }
    }
  }

  @override
  void dispose() {
    _nameController.dispose();
    _phoneController.dispose();
    _addressController.dispose();
    _latController.dispose();
    _longController.dispose();
    super.dispose();
  }

  Future<void> _getCurrentLocation() async {
    setState(() => _isLoading = true);
    try {
      bool serviceEnabled = await Geolocator.isLocationServiceEnabled();
      if (!serviceEnabled) {
        _showError('خدمة الموقع غير مفعلة');
        return;
      }
      LocationPermission permission = await Geolocator.checkPermission();
      if (permission == LocationPermission.denied) {
        permission = await Geolocator.requestPermission();
        if (permission == LocationPermission.denied) {
          _showError('تم رفض إذن الموقع');
          return;
        }
      }
      if (permission == LocationPermission.deniedForever) {
        _showError('تم رفض إذن الموقع نهائياً');
        return;
      }
      final pos = await Geolocator.getCurrentPosition(
        locationSettings: const LocationSettings(
          accuracy: LocationAccuracy.high,
        ),
      );
      setState(() {
        _latController.text = pos.latitude.toString();
        _longController.text = pos.longitude.toString();
        _locationMethod = 'gps';
        _useMyLocation = true;
      });
      _findClosestGovernorate(pos.latitude, pos.longitude);
    } catch (e) {
      _showError('فشل الحصول على الموقع: $e');
    } finally {
      setState(() => _isLoading = false);
    }
  }

  void _findClosestGovernorate(double lat, double lng) {
    EgyptGovernorate? best;
    double bestDist = double.infinity;
    for (final g in egyptGovernorates) {
      if (g.latitude == 0 && g.longitude == 0) continue;
      final dx = lat - g.latitude;
      final dy = lng - g.longitude;
      final d = dx * dx + dy * dy;
      if (d < bestDist) {
        bestDist = d;
        best = g;
      }
    }
    if (best != null) setState(() => _selectedGovernorate = best);
  }

  void _showError(String msg) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(msg),
        backgroundColor: Theme.of(context).colorScheme.error,
      ),
    );
  }

  Future<void> _saveCustomer() async {
    if (!_formKey.currentState!.validate()) return;
    final notifier = ref.read(customersListProvider.notifier);
    final customer = Customer.create(
      name: _nameController.text.trim(),
      phone: _phoneController.text.trim().isNotEmpty
          ? _phoneController.text.trim()
          : null,
      address: _addressController.text.trim().isNotEmpty
          ? _addressController.text.trim()
          : null,
      locationMethod: _locationMethod,
      governorateId: _selectedGovernorate?.id,
      latitude: _latController.text.isNotEmpty
          ? double.tryParse(_latController.text)
          : null,
      longitude: _longController.text.isNotEmpty
          ? double.tryParse(_longController.text)
          : null,
    );
    if (_isEditing) {
      final updated = customer.copyWith(id: widget.customer!.id);
      await notifier.updateCustomer(updated);
    } else {
      await notifier.add(customer);
    }
    if (mounted) Navigator.of(context).pop();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text(_isEditing ? 'تعديل العميل' : 'عميل جديد')),
      body: Form(
        key: _formKey,
        child: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            TextFormField(
              controller: _nameController,
              decoration: const InputDecoration(
                labelText: 'الاسم*',
                prefixIcon: Icon(Icons.person),
              ),
              validator: (v) => (v == null || v.isEmpty) ? 'الاسم مطلوب' : null,
            ),
            const SizedBox(height: 16),
            TextFormField(
              controller: _phoneController,
              decoration: const InputDecoration(
                labelText: 'رقم الهاتف',
                prefixIcon: Icon(Icons.phone),
              ),
              keyboardType: TextInputType.phone,
            ),
            const SizedBox(height: 16),
            TextFormField(
              controller: _addressController,
              decoration: const InputDecoration(
                labelText: 'العنوان',
                prefixIcon: Icon(Icons.location_on),
              ),
            ),
            const SizedBox(height: 16),
            DropdownButtonFormField<EgyptGovernorate?>(
              initialValue: _selectedGovernorate,
              decoration: const InputDecoration(
                labelText: 'المحافظة',
                prefixIcon: Icon(Icons.place),
              ),
              items: egyptGovernorates
                  .map((g) => DropdownMenuItem(value: g, child: Text(g.nameAr)))
                  .toList(),
              onChanged: (v) => setState(() => _selectedGovernorate = v),
            ),
            const SizedBox(height: 16),
            OutlinedButton.icon(
              onPressed: _isLoading ? null : _getCurrentLocation,
              icon: _isLoading
                  ? const SizedBox(
                      width: 20,
                      height: 20,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : const Icon(Icons.my_location),
              label: Text(
                _useMyLocation ? 'تم استخدام موقعي' : 'استخدم موقعي الحالي',
              ),
            ),
            const SizedBox(height: 16),
            if (_locationMethod == 'manual' || _useMyLocation) ...[
              const Text('الإحداثيات (اختياري)'),
              const SizedBox(height: 8),
              Row(
                children: [
                  Expanded(
                    child: TextFormField(
                      controller: _latController,
                      decoration: const InputDecoration(
                        labelText: 'خط العرض (Latitude)',
                        prefixIcon: Icon(Icons.straighten),
                      ),
                      keyboardType: const TextInputType.numberWithOptions(
                        decimal: true,
                      ),
                    ),
                  ),
                  const SizedBox(width: 16),
                  Expanded(
                    child: TextFormField(
                      controller: _longController,
                      decoration: const InputDecoration(
                        labelText: 'خط الطول (Longitude)',
                        prefixIcon: Icon(Icons.straighten),
                      ),
                      keyboardType: const TextInputType.numberWithOptions(
                        decimal: true,
                      ),
                    ),
                  ),
                ],
              ),
            ],
            const SizedBox(height: 32),
            ElevatedButton(
              onPressed: _saveCustomer,
              style: ElevatedButton.styleFrom(
                minimumSize: const Size(double.infinity, 48),
              ),
              child: Text(_isEditing ? 'تحديث' : 'حفظ العميل'),
            ),
            const SizedBox(height: 16),
          ],
        ),
      ),
    );
  }
}
