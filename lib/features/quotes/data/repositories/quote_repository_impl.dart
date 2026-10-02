import '../../../../core/database/database_helper.dart';
import '../../../../core/errors/app_exception.dart';
import '../models/quote.dart';
import 'quote_repository.dart';

class QuoteRepositoryImpl implements QuoteRepository {
  final DatabaseHelper _db;

  QuoteRepositoryImpl(this._db);

  @override
  Future<List<Quote>> getAll({String? status, int? customerId}) async {
    try {
      return await _db.getQuotes(status: status, customerId: customerId);
    } catch (e) {
      throw DatabaseException('Failed to get quotes: $e');
    }
  }

  @override
  Future<Quote?> getById(int id) async {
    try {
      return await _db.getQuote(id);
    } catch (e) {
      throw DatabaseException('Failed to get quote: $e');
    }
  }

  @override
  Future<int> insert(Quote quote) async {
    try {
      return await _db.insertQuote(quote);
    } catch (e) {
      throw DatabaseException('Failed to insert quote: $e');
    }
  }

  @override
  Future<int> update(Quote quote) async {
    try {
      return await _db.updateQuote(quote);
    } catch (e) {
      throw DatabaseException('Failed to update quote: $e');
    }
  }

  @override
  Future<int> delete(int id) async {
    try {
      return await _db.deleteQuote(id);
    } catch (e) {
      throw DatabaseException('Failed to delete quote: $e');
    }
  }

  @override
  Future<List<Quote>> getByCustomerId(int customerId) async {
    try {
      return await _db.getQuotes(customerId: customerId);
    } catch (e) {
      throw DatabaseException('Failed to get quotes by customer: $e');
    }
  }
}
