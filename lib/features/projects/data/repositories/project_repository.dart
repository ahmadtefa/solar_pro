import '../models/project.dart';

abstract class ProjectRepository {
  Future<List<Project>> getAll({String? status});
  Future<Project?> getById(int id);
  Future<int> insert(Project project);
  Future<int> update(Project project);
  Future<int> delete(int id);
  Future<List<Project>> getByQuoteId(int quoteId);
}
