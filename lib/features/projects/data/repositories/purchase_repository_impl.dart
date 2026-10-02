import '../../../../core/database/database_helper.dart';
import '../../../../core/errors/app_exception.dart';
import '../models/purchase.dart';
import 'purchase_repository.dart';

class PurchaseRepositoryImpl implements PurchaseRepository {
  final DatabaseHelper _db;

  PurchaseRepositoryImpl(this._db);

  @override
  Future<List<Purchase>> getByProjectId(int projectId) async {
    try {
      return await _db.getPurchases(projectId);
    } catch (e) {
      throw DatabaseException('Failed to get purchases: $e');
    }
  }

  @override
  Future<int> insert(Purchase purchase) async {
    try {
      return await _db.insertPurchase(purchase);
    } catch (e) {
      throw DatabaseException('Failed to insert purchase: $e');
    }
  }

  @override
  Future<int> update(Purchase purchase) async {
    try {
      return await _db.updatePurchase(purchase);
    } catch (e) {
      throw DatabaseException('Failed to update purchase: $e');
    }
  }

  @override
  Future<int> delete(int id) async {
    try {
      return await _db.deletePurchase(id);
    } catch (e) {
      throw DatabaseException('Failed to delete purchase: $e');
    }
  }

  @override
  Future<double> getTotalCost(int projectId) async {
    try {
      final result = await _db.rawQueryList(
        'SELECT COALESCE(SUM(price), 0) as total FROM purchases WHERE projectId = ?',
        [projectId],
      );
      if (result.isEmpty) return 0;
      return (result.first['total'] as num?)?.toDouble() ?? 0;
    } catch (e) {
      throw DatabaseException('Failed to get total cost: $e');
    }
  }
}
