import '../models/design.dart';

abstract class DesignRepository {
  Future<List<Design>> getAll({int? customerId});
  Future<Design?> getById(int id);
  Future<int> insert(Design design);
  Future<int> update(Design design);
  Future<int> delete(int id);
}
