import '../models/customer.dart';

abstract class CustomerRepository {
  Future<List<Customer>> getAll();
  Future<Customer?> getById(int id);
  Future<int> insert(Customer customer);
  Future<int> update(Customer customer);
  Future<int> delete(int id);
  Future<List<Customer>> search(String query);
}
