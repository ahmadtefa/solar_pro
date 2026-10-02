import '../models/quote_item.dart';

abstract class QuoteItemRepository {
  Future<List<QuoteItem>> getByQuoteId(int quoteId);
  Future<int> insert(QuoteItem item);
  Future<int> update(QuoteItem item);
  Future<int> delete(int id);
  Future<int> deleteByQuoteId(int quoteId);
}
