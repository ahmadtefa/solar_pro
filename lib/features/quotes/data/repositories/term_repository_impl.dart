import '../../../../core/database/database_helper.dart';
import '../../../../core/errors/app_exception.dart';
import '../models/term.dart';
import 'term_repository.dart';

class TermRepositoryImpl implements TermRepository {
  final DatabaseHelper _db;

  TermRepositoryImpl(this._db);

  @override
  Future<List<Term>> getByQuoteId(int quoteId) async {
    try {
      return await _db.getTerms(quoteId);
    } catch (e) {
      throw DatabaseException('Failed to get terms: $e');
    }
  }

  @override
  Future<int> insert(Term term) async {
    try {
      return await _db.insertTerm(term);
    } catch (e) {
      throw DatabaseException('Failed to insert term: $e');
    }
  }

  @override
  Future<int> update(Term term) async {
    try {
      return await _db.updateTerm(term);
    } catch (e) {
      throw DatabaseException('Failed to update term: $e');
    }
  }

  @override
  Future<int> delete(int id) async {
    try {
      return await _db.deleteTerm(id);
    } catch (e) {
      throw DatabaseException('Failed to delete term: $e');
    }
  }

  @override
  Future<int> deleteByQuoteId(int quoteId) async {
    try {
      return await _db.delete('terms', where: 'quoteId = ?', whereArgs: [quoteId]);
    } catch (e) {
      throw DatabaseException('Failed to delete terms: $e');
    }
  }
}
