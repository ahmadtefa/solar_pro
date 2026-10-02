import '../models/component.dart';

abstract class ComponentRepository {
  Future<List<Component>> getAll({String? type});
  Future<Component?> getById(int id);
  Future<int> insert(Component component);
  Future<int> update(Component component);
  Future<int> delete(int id);
}
