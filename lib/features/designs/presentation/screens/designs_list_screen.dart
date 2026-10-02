import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../data/models/design.dart';
import '../providers/design_providers.dart';
import 'design_form_screen.dart';

class DesignsListScreen extends ConsumerStatefulWidget {
  const DesignsListScreen({super.key});

  @override
  ConsumerState<DesignsListScreen> createState() => _DesignsListScreenState();
}

class _DesignsListScreenState extends ConsumerState<DesignsListScreen> {
  Future<void> _openForm(BuildContext context, {Design? design}) async {
    await Navigator.of(context).push(
      MaterialPageRoute(
        builder: (_) => DesignFormScreen(design: design),
      ),
    );
    ref.invalidate(designsListProvider);
  }

  Future<void> _confirmDelete(BuildContext context, Design design) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('حذف التصميم'),
        content: Text(
          'هل أنت متأكد من حذف تصميم "${design.createdAt.toLocal()}"؟\nلا يمكن التراجع عن هذه العملية.',
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

    if (confirmed == true && mounted) {
      final notifier = ref.read(designsListProvider.notifier);
      await notifier.deleteDesign(design.id!);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('التصميمات'),
      ),
      body: Consumer(
        builder: (context, ref, _) {
          final designsAsync = ref.watch(designsListProvider);

          return designsAsync.when(
            loading: () => const Center(child: CircularProgressIndicator()),
            error: (error, _) => Center(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  const Icon(Icons.error_outline, size: 48, color: Colors.redAccent),
                  const SizedBox(height: 8),
                  Text('خطأ: $error', style: const TextStyle(color: Colors.red)),
                ],
              ),
            ),
            data: (designs) {
              if (designs.isEmpty) {
                return Center(
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Icon(Icons.design_services,
                          size: 64, color: Theme.of(context).colorScheme.outline),
                      const SizedBox(height: 12),
                      Text(
                        'لا توجد تصاميم بعد',
                        style: Theme.of(context).textTheme.titleMedium?.copyWith(
                              color: Theme.of(context).colorScheme.outline,
                            ),
                      ),
                      const SizedBox(height: 8),
                      Text(
                        'اضغط على زر الإضافة لبدء تصميم جديد',
                        style: Theme.of(context).textTheme.bodySmall?.copyWith(
                              color: Theme.of(context).colorScheme.outline,
                            ),
                      ),
                    ],
                  ),
                );
              }

              return ListView.builder(
                padding: const EdgeInsets.all(16),
                itemCount: designs.length,
                itemBuilder: (context, index) {
                  final design = designs[index];
                  return Card(
                    margin: const EdgeInsets.only(bottom: 12),
                    child: ListTile(
                      leading: CircleAvatar(
                        backgroundColor: Theme.of(context).colorScheme.primaryContainer,
                        child: Icon(Icons.design_services,
                            color: Theme.of(context).colorScheme.onPrimaryContainer),
                      ),
                      title: Text(_formatDate(design.createdAt)),
                      subtitle: Text('${design.capacityKw} ك.و · ${design.systemType}'),
                      trailing: Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          IconButton(
                            icon: const Icon(Icons.edit),
                            onPressed: () => _openForm(context, design: design),
                          ),
                          IconButton(
                            icon: Icon(Icons.delete, color: Colors.red),
                            onPressed: () => _confirmDelete(context, design),
                          ),
                        ],
                      ),
                      onTap: () => _openForm(context, design: design),
                    ),
                  );
                },
              );
            },
          );
        },
      ),
      floatingActionButton: FloatingActionButton.extended(
        heroTag: 'designs_fab',
        onPressed: () => _openForm(context),
        icon: const Icon(Icons.add),
        label: const Text('تصميم جديد'),
      ),
    );
  }

  String _formatDate(DateTime date) {
    return '${date.day}/${date.month}/${date.year} ${date.hour}:${date.minute.toString().padLeft(2, '0')}';
  }
}
