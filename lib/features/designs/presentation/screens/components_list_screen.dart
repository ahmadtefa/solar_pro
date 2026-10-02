import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../data/models/component.dart';
import '../providers/component_providers.dart';
import 'component_form_screen.dart';

class ComponentsListScreen extends ConsumerStatefulWidget {
  const ComponentsListScreen({super.key});

  @override
  ConsumerState<ComponentsListScreen> createState() =>
      _ComponentsListScreenState();
}

class _ComponentsListScreenState extends ConsumerState<ComponentsListScreen>
    with SingleTickerProviderStateMixin {
  late final TabController _tabController;

  @override
  void initState() {
    super.initState();
    _tabController = TabController(length: 2, vsync: this);
  }

  @override
  void dispose() {
    _tabController.dispose();
    super.dispose();
  }

  // Opens the form for add or edit, then refreshes both lists on return.
  Future<void> _openForm(BuildContext context, {Component? component}) async {
    await Navigator.of(context).push(
      MaterialPageRoute(
        builder: (_) => ComponentFormScreen(component: component),
      ),
    );
    // Refresh both lists in case the type changed during an edit.
    ref.invalidate(panelsListProvider);
    ref.invalidate(invertersListProvider);
  }

  Future<void> _confirmDelete(
    BuildContext context,
    WidgetRef ref,
    Component component,
  ) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('حذف المكوّن'),
        content: Text(
          'هل أنت متأكد من حذف "${component.brand} ${component.model}"؟\nلا يمكن التراجع عن هذه العملية.',
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

    if (confirmed == true && context.mounted) {
      final isPanelTab = _tabController.index == 0;
      final notifier = isPanelTab
          ? ref.read(panelsListProvider.notifier)
          : ref.read(invertersListProvider.notifier);
      await notifier.deleteComponent(component.id!);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('المكونات'),
        bottom: TabBar(
          controller: _tabController,
          tabs: const [
            Tab(icon: Icon(Icons.solar_power), text: 'الألواح'),
            Tab(icon: Icon(Icons.electrical_services), text: 'الإنفرترات'),
          ],
        ),
      ),
      body: TabBarView(
        controller: _tabController,
        children: [
          _ComponentTab(
            provider: panelsListProvider,
            emptyLabel: 'لا توجد ألواح شمسية بعد',
            onEdit: (c) => _openForm(context, component: c),
            onDelete: (c) => _confirmDelete(context, ref, c),
          ),
          _ComponentTab(
            provider: invertersListProvider,
            emptyLabel: 'لا توجد إنفرترات بعد',
            onEdit: (c) => _openForm(context, component: c),
            onDelete: (c) => _confirmDelete(context, ref, c),
          ),
        ],
      ),
      floatingActionButton: FloatingActionButton.extended(
        heroTag: 'components_fab',
        onPressed: () => _openForm(context),
        icon: const Icon(Icons.add),
        label: const Text('مكوّن جديد'),
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// Tab content (loading / empty / list)
// ---------------------------------------------------------------------------

class _ComponentTab extends ConsumerWidget {
  final AsyncNotifierProvider<dynamic, List<Component>> provider;
  final String emptyLabel;
  final void Function(Component) onEdit;
  final void Function(Component) onDelete;

  const _ComponentTab({
    required this.provider,
    required this.emptyLabel,
    required this.onEdit,
    required this.onDelete,
  });

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final asyncValue = ref.watch(provider);

    return asyncValue.when(
      loading: () => const Center(child: CircularProgressIndicator()),
      error: (error, _) => Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.error_outline,
                size: 48, color: Colors.redAccent),
            const SizedBox(height: 8),
            Text('خطأ: $error', style: const TextStyle(color: Colors.red)),
          ],
        ),
      ),
      data: (components) {
        if (components.isEmpty) {
          return Center(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(Icons.inbox_outlined,
                    size: 64, color: Theme.of(context).colorScheme.outline),
                const SizedBox(height: 12),
                Text(
                  emptyLabel,
                  style: Theme.of(context).textTheme.titleMedium?.copyWith(
                        color: Theme.of(context).colorScheme.outline,
                      ),
                ),
              ],
            ),
          );
        }

        return ListView.builder(
          itemCount: components.length,
          itemBuilder: (context, index) {
            final c = components[index];
            return _ComponentTile(
              component: c,
              onEdit: () => onEdit(c),
              onDelete: () => onDelete(c),
            );
          },
        );
      },
    );
  }
}

// ---------------------------------------------------------------------------
// Single list tile with swipe-to-delete
// ---------------------------------------------------------------------------

class _ComponentTile extends StatelessWidget {
  final Component component;
  final VoidCallback onEdit;
  final VoidCallback onDelete;

  const _ComponentTile({
    required this.component,
    required this.onEdit,
    required this.onDelete,
  });

  String _specs() {
    final c = component;
    if (c.type == ComponentType.panel.value) {
      final parts = <String>[];
      if (c.powerW != null) parts.add('${c.powerW} W');
      if (c.vocV != null) parts.add('Voc: ${c.vocV} V');
      return parts.join(' · ');
    } else {
      final parts = <String>[];
      if (c.powerKw != null) parts.add('${c.powerKw} kW');
      if (c.powerHp != null) parts.add('${c.powerHp?.toStringAsFixed(1)} HP');
      if (c.maxDcVoltage != null) parts.add('DC: ${c.maxDcVoltage} V');
      return parts.join(' · ');
    }
  }

  String _priceDisplay() {
    final c = component;
    if (c.type == ComponentType.panel.value) {
      if (c.pricePerWatt != null) {
        return 'سعر الواط: ${c.pricePerWatt!.toStringAsFixed(2)} ج.م';
      }
      return 'لا يوجد سعر';
    } else {
      return '${c.price.toStringAsFixed(0)} ج.م';
    }
  }

  @override
  Widget build(BuildContext context) {
    return Dismissible(
      key: ValueKey(component.id),
      direction: DismissDirection.endToStart,
      background: Container(
        alignment: Alignment.centerRight,
        padding: const EdgeInsets.symmetric(horizontal: 20),
        color: Theme.of(context).colorScheme.error,
        child: const Icon(Icons.delete, color: Colors.white),
      ),
      confirmDismiss: (_) async {
        onDelete();
        return false;
      },
      child: ListTile(
        leading: CircleAvatar(
          backgroundColor: component.type == ComponentType.panel.value
              ? Colors.orange.shade100
              : Colors.blue.shade100,
          child: Icon(
            component.type == ComponentType.panel.value
                ? Icons.solar_power
                : Icons.electrical_services,
            color: component.type == ComponentType.panel.value
                ? Colors.orange.shade700
                : Colors.blue.shade700,
          ),
        ),
        title: Text('${component.brand} ${component.model}'),
        subtitle: Text(_specs()),
        trailing: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(
              _priceDisplay(),
              style: Theme.of(context).textTheme.bodySmall?.copyWith(
                    color: Theme.of(context).colorScheme.primary,
                    fontWeight: FontWeight.bold,
                  ),
            ),
            const SizedBox(width: 8),
            const Icon(Icons.chevron_right),
          ],
        ),
        onTap: onEdit,
      ),
    );
  }
}
