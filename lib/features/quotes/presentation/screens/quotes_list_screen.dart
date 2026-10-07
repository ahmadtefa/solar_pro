import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../../core/utils/currency_formatter.dart';
import '../../../customers/data/models/customer.dart';
import '../../../designs/presentation/providers/design_providers.dart';
import '../../data/models/quote.dart';
import '../providers/quote_providers.dart';
import '../widgets/quote_status_badge.dart';
import 'quote_details_screen.dart';
import 'quote_form_screen.dart';

/// Lists every quotation with a status filter and a text search.
class QuotesListScreen extends ConsumerStatefulWidget {
  const QuotesListScreen({super.key});

  @override
  ConsumerState<QuotesListScreen> createState() => _QuotesListScreenState();
}

class _QuotesListScreenState extends ConsumerState<QuotesListScreen> {
  String? _statusFilter; // null == all
  String _search = '';

  Future<void> _openForm(BuildContext context, {Quote? quote}) async {
    await Navigator.of(context).push(
      MaterialPageRoute(builder: (_) => QuoteFormScreen(quote: quote)),
    );
    if (mounted) ref.invalidate(quotesListProvider);
  }

  Future<void> _openDetails(BuildContext context, Quote quote) async {
    await Navigator.of(context).push(
      MaterialPageRoute(builder: (_) => QuoteDetailsScreen(quote: quote)),
    );
    if (mounted) ref.invalidate(quotesListProvider);
  }

  Future<void> _confirmDelete(BuildContext context, Quote quote) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('حذف عرض السعر'),
        content: Text(
          'هل أنت متأكد من حذف العرض رقم "${quote.displayNumber}"؟\nلا يمكن التراجع عن هذه العملية.',
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

    if (confirmed != true || !mounted) return;
    final notifier = ref.read(quotesListProvider.notifier);
    await notifier.deleteQuote(quote.id!);
  }

  @override
  Widget build(BuildContext context) {
    final quotesAsync = ref.watch(quotesListProvider);
    final customersAsync = ref.watch(customersForDropdownProvider);

    final customerNames = <int, String>{
      for (final customer
          in customersAsync.valueOrNull ?? <Customer>[])
        customer.id!: customer.name,
    };

    return Scaffold(
      appBar: AppBar(
        title: const Text('عروض الأسعار'),
        actions: [
          IconButton(
            tooltip: 'تحديث',
            icon: const Icon(Icons.refresh),
            onPressed: () => ref.read(quotesListProvider.notifier).refresh(),
          ),
        ],
      ),
      body: Column(
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 12, 16, 4),
            child: TextField(
              decoration: InputDecoration(
                labelText: 'بحث بالعميل أو رقم العرض',
                prefixIcon: const Icon(Icons.search),
                border: const OutlineInputBorder(),
                isDense: true,
                suffixIcon: _search.isEmpty
                    ? null
                    : IconButton(
                        icon: const Icon(Icons.clear),
                        onPressed: () => setState(() => _search = ''),
                      ),
              ),
              onChanged: (value) => setState(() => _search = value.trim()),
            ),
          ),
          SizedBox(
            height: 52,
            child: ListView(
              scrollDirection: Axis.horizontal,
              padding: const EdgeInsets.symmetric(horizontal: 12),
              children: [
                _filterChip(context, null, 'الكل'),
                for (final status in QuoteStatus.values)
                  _filterChip(context, status.value, status.labelAr),
              ],
            ),
          ),
          Expanded(
            child: quotesAsync.when(
              loading: () => const Center(child: CircularProgressIndicator()),
              error: (error, _) => Center(
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    const Icon(Icons.error_outline,
                        size: 48, color: Colors.redAccent),
                    const SizedBox(height: 8),
                    Text('خطأ: $error',
                        style: const TextStyle(color: Colors.red)),
                  ],
                ),
              ),
              data: (quotes) {
                final visible = quotes.where((quote) {
                  final matchesStatus =
                      _statusFilter == null || quote.status == _statusFilter;
                  if (!matchesStatus) return false;
                  if (_search.isEmpty) return true;
                  final name = customerNames[quote.customerId] ?? '';
                  return name.contains(_search) ||
                      quote.displayNumber.contains(_search);
                }).toList();

                if (visible.isEmpty) {
                  return Center(
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Icon(Icons.request_quote_outlined,
                            size: 64,
                            color: Theme.of(context).colorScheme.outline),
                        const SizedBox(height: 12),
                        Text(
                          quotes.isEmpty
                              ? 'لا توجد عروض أسعار بعد'
                              : 'لا توجد نتائج مطابقة',
                          style: Theme.of(context)
                              .textTheme
                              .titleMedium
                              ?.copyWith(
                                color: Theme.of(context).colorScheme.outline,
                              ),
                        ),
                        const SizedBox(height: 8),
                        Text(
                          'اضغط على زر الإضافة لإنشاء عرض سعر جديد',
                          style: Theme.of(context)
                              .textTheme
                              .bodySmall
                              ?.copyWith(
                                color: Theme.of(context).colorScheme.outline,
                              ),
                        ),
                      ],
                    ),
                  );
                }

                return ListView.builder(
                  padding: const EdgeInsets.all(16),
                  itemCount: visible.length,
                  itemBuilder: (context, index) {
                    final quote = visible[index];
                    final customerName =
                        customerNames[quote.customerId] ?? 'عميل غير معروف';
                    return Card(
                      margin: const EdgeInsets.only(bottom: 12),
                      child: ListTile(
                        leading: CircleAvatar(
                          backgroundColor:
                              Theme.of(context).colorScheme.primaryContainer,
                          child: Icon(Icons.request_quote,
                              color: Theme.of(context)
                                  .colorScheme
                                  .onPrimaryContainer),
                        ),
                        title: Text(customerName),
                        subtitle: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            const SizedBox(height: 4),
                            Text(
                              '${quote.displayNumber} · ${_formatDate(quote.createdAt)}',
                            ),
                            const SizedBox(height: 2),
                            Text(
                              CurrencyFormatter.money(quote.totalPrice),
                              style: TextStyle(
                                fontWeight: FontWeight.bold,
                                color: Theme.of(context).colorScheme.primary,
                              ),
                            ),
                            const SizedBox(height: 6),
                            QuoteStatusBadge(status: quote.status),
                          ],
                        ),
                        trailing: Row(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            IconButton(
                              icon: const Icon(Icons.edit),
                              tooltip: 'تعديل',
                              onPressed: () => _openForm(context, quote: quote),
                            ),
                            IconButton(
                              icon: const Icon(Icons.delete, color: Colors.red),
                              tooltip: 'حذف',
                              onPressed: () => _confirmDelete(context, quote),
                            ),
                          ],
                        ),
                        onTap: () => _openDetails(context, quote),
                      ),
                    );
                  },
                );
              },
            ),
          ),
        ],
      ),
      floatingActionButton: FloatingActionButton.extended(
        heroTag: 'quotes_fab',
        onPressed: () => _openForm(context),
        icon: const Icon(Icons.add),
        label: const Text('عرض سعر جديد'),
      ),
    );
  }

  Widget _filterChip(BuildContext context, String? value, String label) {
    final selected = _statusFilter == value;
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 4),
      child: FilterChip(
        label: Text(label),
        selected: selected,
        onSelected: (_) => setState(() => _statusFilter = value),
      ),
    );
  }

  String _formatDate(DateTime date) {
    final local = date.toLocal();
    return '${local.year}/${local.month.toString().padLeft(2, '0')}/${local.day.toString().padLeft(2, '0')}';
  }
}
