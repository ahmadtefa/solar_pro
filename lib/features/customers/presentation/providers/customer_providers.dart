import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../data/repositories/customer_repository.dart';
import '../../data/repositories/customer_repository_impl.dart';
import '../../../../core/database/database_helper.dart';
import '../../data/models/customer.dart';

// Repository provider
final customerRepositoryProvider = Provider<CustomerRepository>((ref) {
  return CustomerRepositoryImpl(DatabaseHelper.instance);
});

// AsyncNotifier for CRUD operations
class CustomersNotifier extends AsyncNotifier<List<Customer>> {
  @override
  Future<List<Customer>> build() async {
    return _fetchAll();
  }

  Future<List<Customer>> _fetchAll() async {
    final repository = ref.read(customerRepositoryProvider);
    return repository.getAll();
  }

  Future<void> refresh() async {
    state = const AsyncValue.loading();
    state = await AsyncValue.guard(() => _fetchAll());
  }

  Future<int?> add(Customer customer) async {
    final repository = ref.read(customerRepositoryProvider);
    final id = await AsyncValue.guard(() => repository.insert(customer));
    id.whenOrNull(
      data: (insertedId) {
        ref.invalidate(customerByIdProvider(insertedId));
        refresh();
      },
      error: (e, st) {},
    );
    return id.valueOrNull;
  }

  Future<int?> updateCustomer(Customer customer) async {
    final repository = ref.read(customerRepositoryProvider);
    final rows = await AsyncValue.guard(() => repository.update(customer));
    rows.whenOrNull(
      data: (updatedRows) {
        if (customer.id != null) {
          ref.invalidate(customerByIdProvider(customer.id!));
        }
        refresh();
      },
      error: (e, st) {},
    );
    return rows.valueOrNull;
  }

  Future<int?> deleteCustomer(int id) async {
    final repository = ref.read(customerRepositoryProvider);
    final rows = await AsyncValue.guard(() => repository.delete(id));
    rows.whenOrNull(
      data: (deletedRows) {
        ref.invalidate(customerByIdProvider(id));
        refresh();
      },
      error: (e, st) {},
    );
    return rows.valueOrNull;
  }
}

final customersListProvider =
    AsyncNotifierProvider<CustomersNotifier, List<Customer>>(CustomersNotifier.new);

// family provider for single customer
final customerByIdProvider = FutureProvider.family<Customer?, int>((ref, id) async {
  final repository = ref.read(customerRepositoryProvider);
  return repository.getById(id);
});

// search provider
final customersSearchProvider = FutureProvider.family<List<Customer>, String>((ref, query) async {
  final repository = ref.read(customerRepositoryProvider);
  return repository.search(query);
});
