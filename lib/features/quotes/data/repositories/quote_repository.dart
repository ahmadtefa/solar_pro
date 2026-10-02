import '../models/quote.dart';

abstract class QuoteRepository {
  Future<List<Quote>> getAll({String? status, int? customerId});
  Future<Quote?> getById(int id);
  Future<int> insert(Quote quote);
  Future<int> update(Quote quote);
  Future<int> delete(int id);
  Future<List<Quote>> getByCustomerId(int customerId);
}
