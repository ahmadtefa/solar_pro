import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../data/models/component.dart';
import '../../data/repositories/component_repository.dart';
import '../../data/repositories/component_repository_impl.dart';
import '../../../../core/database/database_helper.dart';

// ---------------------------------------------------------------------------
// Repository provider
// ---------------------------------------------------------------------------

final componentRepositoryProvider = Provider<ComponentRepository>((ref) {
  return ComponentRepositoryImpl(DatabaseHelper.instance);
});

// ---------------------------------------------------------------------------
// Generic notifier — shared logic for panels and inverters
// ---------------------------------------------------------------------------

class ComponentsNotifier extends AsyncNotifier<List<Component>> {
  final String? typeFilter;

  ComponentsNotifier({this.typeFilter});

  @override
  Future<List<Component>> build() => _fetchAll();

  Future<List<Component>> _fetchAll() {
    final repo = ref.read(componentRepositoryProvider);
    return repo.getAll(type: typeFilter);
  }

  Future<void> refresh() async {
    state = const AsyncValue.loading();
    state = await AsyncValue.guard(_fetchAll);
  }

  Future<int?> add(Component component) async {
    final repo = ref.read(componentRepositoryProvider);
    final id = await repo.insert(component);
    ref.invalidate(componentByIdProvider(id));
    await refresh();
    return id;
  }

  Future<int?> updateComponent(Component component) async {
    final repo = ref.read(componentRepositoryProvider);
    final rows = await repo.update(component);
    if (component.id != null) {
      ref.invalidate(componentByIdProvider(component.id!));
    }
    await refresh();
    return rows;
  }

  Future<int?> deleteComponent(int id) async {
    final repo = ref.read(componentRepositoryProvider);
    final rows = await repo.delete(id);
    ref.invalidate(componentByIdProvider(id));
    await refresh();
    return rows;
  }
}

// ---------------------------------------------------------------------------
// Panels provider (type == 'panel')
// ---------------------------------------------------------------------------

final panelsListProvider =
    AsyncNotifierProvider<ComponentsNotifier, List<Component>>(
      () => ComponentsNotifier(typeFilter: ComponentType.panel.value),
    );

// ---------------------------------------------------------------------------
// Inverters provider (type == 'inverter')
// ---------------------------------------------------------------------------

final invertersListProvider =
    AsyncNotifierProvider<ComponentsNotifier, List<Component>>(
      () => ComponentsNotifier(typeFilter: ComponentType.inverter.value),
    );

// ---------------------------------------------------------------------------
// Single component by id (family)
// ---------------------------------------------------------------------------

final componentByIdProvider = FutureProvider.family<Component?, int>((
  ref,
  id,
) async {
  final repo = ref.read(componentRepositoryProvider);
  return repo.getById(id);
});
