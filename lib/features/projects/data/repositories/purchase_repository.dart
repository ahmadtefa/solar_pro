import '../models/purchase.dart';

abstract class PurchaseRepository {
  Future<List<Purchase>> getByProjectId(int projectId);
  Future<int> insert(Purchase purchase);
  Future<int> update(Purchase purchase);
  Future<int> delete(int id);
  Future<double> getTotalCost(int projectId);
}
