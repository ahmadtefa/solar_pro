import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../../core/constants/egypt_governorates.dart';
import '../providers/customer_providers.dart';
import '../../../customers/data/models/customer.dart';
import 'customer_form_screen.dart';

class CustomerDetailsScreen extends ConsumerWidget {
  final int customerId;

  const CustomerDetailsScreen({super.key, required this.customerId});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final customerAsync = ref.watch(customerByIdProvider(customerId));

    return Scaffold(
      appBar: AppBar(title: const Text('تفاصيل العميل')),
      body: customerAsync.when(
        data: (Customer? customer) {
          if (customer == null) {
            return const Center(child: Text('العميل غير موجود'));
          }
          return SingleChildScrollView(
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                _buildHeader(context, customer),
                const SizedBox(height: 16),
                _buildLocationSection(context, customer),
                const SizedBox(height: 24),
                _buildActions(context, ref, customer),
              ],
            ),
          );
        },
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (error, _) => Center(child: Text('خطأ: ${error.toString()}')),
      ),
    );
  }

  Widget _buildHeader(BuildContext context, Customer customer) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              customer.name,
              style: Theme.of(context).textTheme.headlineSmall,
            ),
            const SizedBox(height: 8),
            if (customer.phone != null)
              Row(
                children: [
                  const Icon(Icons.phone, size: 20),
                  const SizedBox(width: 8),
                  Text(customer.phone!),
                ],
              ),
            if (customer.address != null)
              Row(
                children: [
                  const Icon(Icons.location_on, size: 20),
                  const SizedBox(width: 8),
                  Expanded(child: Text(customer.address!)),
                ],
              ),
          ],
        ),
      ),
    );
  }

  Widget _buildLocationSection(BuildContext context, Customer customer) {
    if (customer.latitude == null || customer.longitude == null) {
      return const SizedBox.shrink();
    }
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text('الموقع', style: TextStyle(fontWeight: FontWeight.bold)),
            const SizedBox(height: 8),
            Container(
              height: 180,
              decoration: BoxDecoration(
                color: Colors.grey[200],
                borderRadius: BorderRadius.circular(8),
                border: Border.all(color: Colors.grey[300]!),
              ),
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  const Icon(Icons.map, size: 40, color: Colors.grey),
                  const SizedBox(height: 8),
                  Text(
                    'خط العرض: ${customer.latitude}',
                    style: Theme.of(context).textTheme.bodyMedium,
                  ),
                  Text(
                    'خط الطول: ${customer.longitude}',
                    style: Theme.of(context).textTheme.bodyMedium,
                  ),
                  const SizedBox(height: 4),
                  Text(
                    'المحافظة: ${_getGovernorateName(customer.governorateId)}',
                    style: Theme.of(context).textTheme.bodySmall,
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildActions(BuildContext context, WidgetRef ref, Customer customer) {
    return Row(
      children: [
        Expanded(
          child: OutlinedButton.icon(
            onPressed: () async {
              await Navigator.of(context).push(
                MaterialPageRoute(
                  builder: (_) => CustomerFormScreen(customer: customer),
                ),
              );
              // Refresh details after editing
              ref.invalidate(customerByIdProvider(customerId));
            },
            icon: const Icon(Icons.edit),
            label: const Text('تعديل'),
          ),
        ),
        const SizedBox(width: 12),
        Expanded(
          child: ElevatedButton.icon(
            onPressed: () => _showDeleteConfirmation(context, ref),
            icon: const Icon(Icons.delete),
            label: const Text('حذف'),
            style: ElevatedButton.styleFrom(
              backgroundColor: Colors.red,
              foregroundColor: Colors.white,
            ),
          ),
        ),
      ],
    );
  }

  void _showDeleteConfirmation(BuildContext context, WidgetRef ref) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('حذف العميل'),
        content: const Text(
          'هل أنت متأكد من حذف هذا العميل؟ لا يمكن التراجع عن هذه العملية.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(false),
            child: const Text('إلغاء'),
          ),
          TextButton(
            onPressed: () => Navigator.of(context).pop(true),
            style: TextButton.styleFrom(foregroundColor: Colors.red),
            child: const Text('حذف'),
          ),
        ],
      ),
    );
    if (confirmed == true && context.mounted) {
      await ref.read(customersListProvider.notifier).deleteCustomer(customerId);
      if (context.mounted) Navigator.of(context).pop();
    }
  }

  String _getGovernorateName(int? id) {
    if (id == null) return '---';
    try {
      return egyptGovernorates.firstWhere((g) => g.id == id).nameAr;
    } catch (_) {
      return '---';
    }
  }
}
