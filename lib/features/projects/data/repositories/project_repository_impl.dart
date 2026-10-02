import '../../../../core/database/database_helper.dart';
import '../../../../core/errors/app_exception.dart';
import '../models/project.dart';
import 'project_repository.dart';

class ProjectRepositoryImpl implements ProjectRepository {
  final DatabaseHelper _db;

  ProjectRepositoryImpl(this._db);

  @override
  Future<List<Project>> getAll({String? status}) async {
    try {
      return await _db.getProjects(status: status);
    } catch (e) {
      throw DatabaseException('Failed to get projects: $e');
    }
  }

  @override
  Future<Project?> getById(int id) async {
    try {
      return await _db.getProject(id);
    } catch (e) {
      throw DatabaseException('Failed to get project: $e');
    }
  }

  @override
  Future<int> insert(Project project) async {
    try {
      return await _db.insertProject(project);
    } catch (e) {
      throw DatabaseException('Failed to insert project: $e');
    }
  }

  @override
  Future<int> update(Project project) async {
    try {
      return await _db.updateProject(project);
    } catch (e) {
      throw DatabaseException('Failed to update project: $e');
    }
  }

  @override
  Future<int> delete(int id) async {
    try {
      return await _db.deleteProject(id);
    } catch (e) {
      throw DatabaseException('Failed to delete project: $e');
    }
  }

  @override
  Future<List<Project>> getByQuoteId(int quoteId) async {
    try {
      final maps = await _db.query('projects', where: 'quoteId = ?', whereArgs: [quoteId]);
      if (maps.isEmpty) return [];
      return [Project.fromMap(maps.first)];
    } catch (e) {
      throw DatabaseException('Failed to get project by quote: $e');
    }
  }
}
