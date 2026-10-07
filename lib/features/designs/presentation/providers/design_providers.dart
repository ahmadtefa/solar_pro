import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../data/models/design.dart';
import '../../../customers/data/models/customer.dart';
import '../../data/repositories/design_repository.dart';
import '../../data/repositories/design_repository_impl.dart';
// One single provider for the customer repository: `design_providers` used to
// declare a second, independent `customerRepositoryProvider`, so overriding one
// of them never affected the screens that read the other. The shared one is
// imported *and* re-exported, so screens that import this file keep working.
import '../../../customers/presentation/providers/customer_providers.dart';
export '../../../customers/presentation/providers/customer_providers.dart';
import '../../../../core/database/database_helper.dart';

// ---------------------------------------------------------------------------
// Repository providers
// ---------------------------------------------------------------------------

final designRepositoryProvider = Provider<DesignRepository>((ref) {
  return DesignRepositoryImpl(DatabaseHelper.instance);
});

// ---------------------------------------------------------------------------
// Customers for dropdown
// ---------------------------------------------------------------------------

final customersForDropdownProvider = FutureProvider<List<Customer>>((ref) async {
  final repo = ref.read(customerRepositoryProvider);
  return repo.getAll();
});

// ---------------------------------------------------------------------------
// Designs list provider (AsyncNotifier)
// ---------------------------------------------------------------------------

class DesignsNotifier extends AsyncNotifier<List<Design>> {
  @override
  Future<List<Design>> build() => _fetchAll();

  Future<List<Design>> _fetchAll() {
    final repo = ref.read(designRepositoryProvider);
    return repo.getAll();
  }

  Future<void> refresh() async {
    state = const AsyncValue.loading();
    state = await AsyncValue.guard(_fetchAll);
  }

  Future<int?> add(Design design) async {
    final repo = ref.read(designRepositoryProvider);
    final id = await repo.insert(design);
    ref.invalidate(designByIdProvider(id));
    await refresh();
    return id;
  }

  Future<int?> updateDesign(Design design) async {
    final repo = ref.read(designRepositoryProvider);
    final rows = await repo.update(design);
    if (design.id != null) {
      ref.invalidate(designByIdProvider(design.id!));
    }
    await refresh();
    return rows;
  }

  Future<int?> deleteDesign(int id) async {
    final repo = ref.read(designRepositoryProvider);
    final rows = await repo.delete(id);
    ref.invalidate(designByIdProvider(id));
    await refresh();
    return rows;
  }
}

final designsListProvider =
    AsyncNotifierProvider<DesignsNotifier, List<Design>>(
      () => DesignsNotifier(),
    );

// ---------------------------------------------------------------------------
// Single design by id (family)
// ---------------------------------------------------------------------------

final designByIdProvider = FutureProvider.family<Design?, int>((
  ref,
  id,
) async {
  final repo = ref.read(designRepositoryProvider);
  return repo.getById(id);
});
