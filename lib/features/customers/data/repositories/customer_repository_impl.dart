import '../../../../core/database/database_helper.dart';
import '../../../../core/errors/app_exception.dart';
import '../models/customer.dart';
import 'customer_repository.dart';

class CustomerRepositoryImpl implements CustomerRepository {
  final DatabaseHelper _db;

  CustomerRepositoryImpl(this._db);

  @override
  Future<List<Customer>> getAll() async {
    try {
      return await _db.getCustomers();
    } catch (e) {
      throw DatabaseException('Failed to get customers: $e');
    }
  }

  @override
  Future<Customer?> getById(int id) async {
    try {
      return await _db.getCustomer(id);
    } catch (e) {
      throw DatabaseException('Failed to get customer: $e');
    }
  }

  @override
  Future<int> insert(Customer customer) async {
    try {
      return await _db.insertCustomer(customer);
    } catch (e) {
      throw DatabaseException('Failed to insert customer: $e');
    }
  }

  @override
  Future<int> update(Customer customer) async {
    try {
      return await _db.updateCustomer(customer);
    } catch (e) {
      throw DatabaseException('Failed to update customer: $e');
    }
  }

  @override
  Future<int> delete(int id) async {
    try {
      return await _db.deleteCustomer(id);
    } catch (e) {
      throw DatabaseException('Failed to delete customer: $e');
    }
  }

  @override
  Future<List<Customer>> search(String query) async {
    try {
      final results = await _db.query(
        'customers',
        where: 'name LIKE ? OR phone LIKE ?',
        whereArgs: ['%$query%', '%$query%'],
        orderBy: 'name',
      );
      return results.map((m) => Customer.fromMap(m)).toList();
    } catch (e) {
      throw DatabaseException('Failed to search customers: $e');
    }
  }
}
