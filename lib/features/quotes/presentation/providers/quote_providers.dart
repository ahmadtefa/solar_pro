import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../../core/database/database_helper.dart';
import '../../../designs/data/models/design.dart';
import '../../../designs/presentation/providers/design_providers.dart';
import '../../../projects/data/models/project.dart';
import '../../../projects/data/repositories/project_repository.dart';
import '../../../projects/data/repositories/project_repository_impl.dart';
import '../../domain/quote_totals.dart';
import '../../data/models/quote.dart';
import '../../data/models/quote_item.dart';
import '../../data/models/term.dart';
import '../../data/repositories/quote_item_repository.dart';
import '../../data/repositories/quote_item_repository_impl.dart';
import '../../data/repositories/quote_repository.dart';
import '../../data/repositories/quote_repository_impl.dart';
import '../../data/repositories/term_repository.dart';
import '../../data/repositories/term_repository_impl.dart';

// ---------------------------------------------------------------------------
// Repository providers
// ---------------------------------------------------------------------------

final quoteRepositoryProvider = Provider<QuoteRepository>((ref) {
  return QuoteRepositoryImpl(DatabaseHelper.instance);
});

final quoteItemRepositoryProvider = Provider<QuoteItemRepository>((ref) {
  return QuoteItemRepositoryImpl(DatabaseHelper.instance);
});

final termRepositoryProvider = Provider<TermRepository>((ref) {
  return TermRepositoryImpl(DatabaseHelper.instance);
});

final projectRepositoryProvider = Provider<ProjectRepository>((ref) {
  return ProjectRepositoryImpl(DatabaseHelper.instance);
});

// ---------------------------------------------------------------------------
// Quotes list + write operations
// ---------------------------------------------------------------------------

class QuotesNotifier extends AsyncNotifier<List<Quote>> {
  @override
  Future<List<Quote>> build() => _fetchAll();

  Future<List<Quote>> _fetchAll() {
    final repo = ref.read(quoteRepositoryProvider);
    return repo.getAll();
  }

  Future<void> refresh() async {
    state = const AsyncValue.loading();
    state = await AsyncValue.guard(_fetchAll);
  }

  /// Saves a quote together with its items and terms.
  ///
  /// The stored `totalPrice` is always recomputed from the items, so the total
  /// can never drift away from the line items. Returns the quote id.
  Future<int> saveQuote({
    required Quote quote,
    required List<QuoteItem> items,
    required List<Term> terms,
  }) async {
    final quoteRepo = ref.read(quoteRepositoryProvider);
    final itemsRepo = ref.read(quoteItemRepositoryProvider);
    final termsRepo = ref.read(termRepositoryProvider);

    final totals = QuoteTotals.compute(
      items: items,
      discountPercent: quote.discount,
      taxPercent: quote.tax,
    );
    final priced = quote.copyWith(totalPrice: totals.total);

    final int quoteId;
    if (priced.id == null) {
      quoteId = await quoteRepo.insert(priced);
    } else {
      await quoteRepo.update(priced);
      quoteId = priced.id!;
      // Replace the children instead of diffing them: a quote has a handful of
      // lines and this keeps the editor (add/remove/reorder) simple.
      await itemsRepo.deleteByQuoteId(quoteId);
      await termsRepo.deleteByQuoteId(quoteId);
    }

    for (var i = 0; i < items.length; i++) {
      await itemsRepo.insert(items[i].copyWith(quoteId: quoteId, orderIndex: i));
    }
    for (var i = 0; i < terms.length; i++) {
      await termsRepo.insert(
        Term.create(quoteId: quoteId, text: terms[i].text, orderIndex: i),
      );
    }

    ref.invalidate(quoteByIdProvider(quoteId));
    ref.invalidate(quoteItemsProvider(quoteId));
    ref.invalidate(quoteTermsProvider(quoteId));
    await refresh();
    return quoteId;
  }

  /// Changes the status of a quote (draft / sent / accepted / rejected / expired).
  Future<bool> updateStatus(int quoteId, String status) async {
    final repo = ref.read(quoteRepositoryProvider);
    final quote = await repo.getById(quoteId);
    if (quote == null) return false;
    await repo.update(quote.copyWith(status: status));
    ref.invalidate(quoteByIdProvider(quoteId));
    await refresh();
    return true;
  }

  Future<int> deleteQuote(int quoteId) async {
    final repo = ref.read(quoteRepositoryProvider);
    final rows = await repo.delete(quoteId);
    ref.invalidate(quoteByIdProvider(quoteId));
    ref.invalidate(quoteItemsProvider(quoteId));
    ref.invalidate(quoteTermsProvider(quoteId));
    ref.invalidate(projectForQuoteProvider(quoteId));
    await refresh();
    return rows;
  }

  /// Turns an accepted quote into an executable project.
  ///
  /// Returns the new project id, or `null` when this quote was already
  /// converted (a project references a quote uniquely).
  Future<int?> convertToProject(int quoteId) async {
    final projectRepo = ref.read(projectRepositoryProvider);
    final existing = await projectRepo.getByQuoteId(quoteId);
    if (existing.isNotEmpty) return null;

    final projectId = await projectRepo.insert(
      Project.create(
        quoteId: quoteId,
        status: ProjectStatus.pending.value,
        startDate: DateTime.now(),
        progressPercent: 0,
      ),
    );
    await updateStatus(quoteId, QuoteStatus.accepted.value);
    ref.invalidate(projectForQuoteProvider(quoteId));
    return projectId;
  }
}

final quotesListProvider =
    AsyncNotifierProvider<QuotesNotifier, List<Quote>>(QuotesNotifier.new);

// ---------------------------------------------------------------------------
// Read providers
// ---------------------------------------------------------------------------

final quoteByIdProvider = FutureProvider.family<Quote?, int>((ref, id) async {
  final repo = ref.read(quoteRepositoryProvider);
  return repo.getById(id);
});

final quoteItemsProvider =
    FutureProvider.family<List<QuoteItem>, int>((ref, quoteId) async {
  final repo = ref.read(quoteItemRepositoryProvider);
  return repo.getByQuoteId(quoteId);
});

final quoteTermsProvider =
    FutureProvider.family<List<Term>, int>((ref, quoteId) async {
  final repo = ref.read(termRepositoryProvider);
  return repo.getByQuoteId(quoteId);
});

/// Designs belonging to a customer, used by the quote editor.
final designsForCustomerProvider =
    FutureProvider.family<List<Design>, int>((ref, customerId) async {
  final repo = ref.read(designRepositoryProvider);
  return repo.getAll(customerId: customerId);
});

/// The project created from a quote, if any.
final projectForQuoteProvider =
    FutureProvider.family<Project?, int>((ref, quoteId) async {
  final repo = ref.read(projectRepositoryProvider);
  final projects = await repo.getByQuoteId(quoteId);
  return projects.isEmpty ? null : projects.first;
});
