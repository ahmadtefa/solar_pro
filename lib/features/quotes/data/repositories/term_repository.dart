import '../models/term.dart';

abstract class TermRepository {
  Future<List<Term>> getByQuoteId(int quoteId);
  Future<int> insert(Term term);
  Future<int> update(Term term);
  Future<int> delete(int id);
  Future<int> deleteByQuoteId(int quoteId);
}
