import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../presentation/providers/customer_providers.dart';
import 'package:flutter/material.dart';
import '../../data/models/customer.dart';

class CustomerListItem extends ConsumerWidget {
  final Customer customer;
  final VoidCallback? onTap;

  const CustomerListItem({
    super.key,
    required this.customer,
    this.onTap,
  });

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return Dismissible(
      key: Key('customer_${customer.id}'),
      direction: DismissDirection.endToStart,
      background: Container(
        alignment: Alignment.centerRight,
        padding: const EdgeInsets.only(right: 20),
        color: Theme.of(context).colorScheme.error,
        child: Icon(
          Icons.delete,
          color: Theme.of(context).colorScheme.onError,
        ),
      ),
      confirmDismiss: (direction) async {
        final confirm = await showDialog<bool>(
          context: context,
          builder: (context) => AlertDialog(
            title: const Text('حذف العميل'),
            content: Text('هل أنت متأكد من حذف العميل ${customer.name}؟'),
            actions: [
              TextButton(
                onPressed: () => Navigator.of(context).pop(false),
                child: const Text('إلغاء'),
              ),
              TextButton(
                onPressed: () => Navigator.of(context).pop(true),
                style: TextButton.styleFrom(
                  foregroundColor: Theme.of(context).colorScheme.error,
                ),
                child: const Text('حذف'),
              ),
            ],
          ),
        );
        if (confirm == true) {
          await ref.read(customersListProvider.notifier).deleteCustomer(customer.id!);
        }
        return confirm;
      },
      onDismissed: (direction) {
        // Deletion is handled in confirmDismiss
      },
      child: ListTile(
        onTap: onTap,
        leading: CircleAvatar(
          child: Text(
            customer.name.isNotEmpty ? customer.name[0] : '?',
            style: const TextStyle(fontWeight: FontWeight.bold),
          ),
        ),
        title: Text(
          customer.name,
          style: Theme.of(context).textTheme.titleMedium,
        ),
        subtitle: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            if (customer.phone != null && customer.phone!.isNotEmpty)
              Text(
                '📱 ${customer.phone}',
                style: Theme.of(context).textTheme.bodySmall,
              ),
            if (customer.address != null && customer.address!.isNotEmpty)
              Text(
                '📍 ${customer.address}',
                style: Theme.of(context).textTheme.bodySmall,
              ),
          ],
        ),
        trailing: const Icon(Icons.chevron_right),
        selected: false,
      ),
    );
  }
}
