import '../../../../core/database/database_helper.dart';
import '../../../../core/errors/app_exception.dart';
import '../models/component.dart';
import 'component_repository.dart';

class ComponentRepositoryImpl implements ComponentRepository {
  final DatabaseHelper _db;

  ComponentRepositoryImpl(this._db);

  @override
  Future<List<Component>> getAll({String? type}) async {
    try {
      return await _db.getComponents(type: type);
    } catch (e) {
      throw DatabaseException('Failed to get components: $e');
    }
  }

  @override
  Future<Component?> getById(int id) async {
    try {
      final maps = await _db.query('components', where: 'id = ?', whereArgs: [id]);
      if (maps.isEmpty) return null;
      return Component.fromMap(maps.first);
    } catch (e) {
      throw DatabaseException('Failed to get component: $e');
    }
  }

  @override
  Future<int> insert(Component component) async {
    print('INSERT: insert() called');
    print('INSERT: component = ${component.toMap()}');
    try {
      return await _db.insertComponent(component);
    } catch (e) {
      throw DatabaseException('Failed to insert component: $e');
    }
  }

  @override
  Future<int> update(Component component) async {
    try {
      return await _db.updateComponent(component);
    } catch (e) {
      throw DatabaseException('Failed to update component: $e');
    }
  }

  @override
  Future<int> delete(int id) async {
    try {
      return await _db.deleteComponent(id);
    } catch (e) {
      throw DatabaseException('Failed to delete component: $e');
    }
  }
}
