import '../../../../core/database/database_helper.dart';
import '../../../../core/errors/app_exception.dart';
import '../models/design.dart';
import 'design_repository.dart';

class DesignRepositoryImpl implements DesignRepository {
  final DatabaseHelper _db;

  DesignRepositoryImpl(this._db);

  @override
  Future<List<Design>> getAll({int? customerId}) async {
    try {
      return await _db.getDesigns(customerId: customerId);
    } catch (e) {
      throw DatabaseException('Failed to get designs: $e');
    }
  }

  @override
  Future<Design?> getById(int id) async {
    try {
      return await _db.getDesign(id);
    } catch (e) {
      throw DatabaseException('Failed to get design: $e');
    }
  }

  @override
  Future<int> insert(Design design) async {
    try {
      return await _db.insertDesign(design);
    } catch (e) {
      throw DatabaseException('Failed to insert design: $e');
    }
  }

  @override
  Future<int> update(Design design) async {
    try {
      return await _db.updateDesign(design);
    } catch (e) {
      throw DatabaseException('Failed to update design: $e');
    }
  }

  @override
  Future<int> delete(int id) async {
    try {
      return await _db.deleteDesign(id);
    } catch (e) {
      throw DatabaseException('Failed to delete design: $e');
    }
  }
}
