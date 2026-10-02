import '../../../../core/database/database_helper.dart';
import '../../../../core/errors/app_exception.dart';
import '../models/quote_item.dart';
import 'quote_item_repository.dart';

class QuoteItemRepositoryImpl implements QuoteItemRepository {
  final DatabaseHelper _db;

  QuoteItemRepositoryImpl(this._db);

  @override
  Future<List<QuoteItem>> getByQuoteId(int quoteId) async {
    try {
      return await _db.getQuoteItems(quoteId);
    } catch (e) {
      throw DatabaseException('Failed to get quote items: $e');
    }
  }

  @override
  Future<int> insert(QuoteItem item) async {
    try {
      return await _db.insertQuoteItem(item);
    } catch (e) {
      throw DatabaseException('Failed to insert quote item: $e');
    }
  }

  @override
  Future<int> update(QuoteItem item) async {
    try {
      return await _db.updateQuoteItem(item);
    } catch (e) {
      throw DatabaseException('Failed to update quote item: $e');
    }
  }

  @override
  Future<int> delete(int id) async {
    try {
      return await _db.deleteQuoteItem(id);
    } catch (e) {
      throw DatabaseException('Failed to delete quote item: $e');
    }
  }

  @override
  Future<int> deleteByQuoteId(int quoteId) async {
    try {
      return await _db.delete('quote_items', where: 'quoteId = ?', whereArgs: [quoteId]);
    } catch (e) {
      throw DatabaseException('Failed to delete quote items: $e');
    }
  }
}
