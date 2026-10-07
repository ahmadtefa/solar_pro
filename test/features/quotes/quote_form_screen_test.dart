import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:solar_pro/features/customers/data/models/customer.dart';
import 'package:solar_pro/features/customers/data/repositories/customer_repository.dart';
import 'package:solar_pro/features/designs/data/models/component.dart';
import 'package:solar_pro/features/designs/data/models/design.dart';
import 'package:solar_pro/features/designs/data/repositories/component_repository.dart';
import 'package:solar_pro/features/designs/data/repositories/design_repository.dart';
import 'package:solar_pro/features/designs/presentation/providers/component_providers.dart';
import 'package:solar_pro/features/designs/presentation/providers/design_providers.dart'
    as designs;
import 'package:solar_pro/features/quotes/data/models/quote.dart';
import 'package:solar_pro/features/quotes/data/models/quote_item.dart';
import 'package:solar_pro/features/quotes/data/models/term.dart';
import 'package:solar_pro/features/quotes/data/repositories/quote_item_repository.dart';
import 'package:solar_pro/features/quotes/data/repositories/quote_repository.dart';
import 'package:solar_pro/features/quotes/data/repositories/term_repository.dart';
import 'package:solar_pro/features/quotes/presentation/providers/quote_providers.dart';
import 'package:solar_pro/features/quotes/presentation/screens/quote_form_screen.dart';
import 'package:solar_pro/features/settings/data/models/app_settings.dart';
import 'package:solar_pro/features/settings/data/repositories/settings_repository.dart';
import 'package:solar_pro/features/settings/presentation/providers/settings_providers.dart';

// ---------------------------------------------------------------------------
// Fakes
// ---------------------------------------------------------------------------

class _FakeCustomerRepository implements CustomerRepository {
  _FakeCustomerRepository(this.items);

  final List<Customer> items;

  @override
  Future<List<Customer>> getAll() async => items;

  @override
  Future<Customer?> getById(int id) async =>
      items.cast<Customer?>().firstWhere((c) => c?.id == id, orElse: () => null);

  @override
  Future<int> insert(Customer customer) async => 1;

  @override
  Future<int> update(Customer customer) async => 1;

  @override
  Future<int> delete(int id) async => 1;

  @override
  Future<List<Customer>> search(String query) async => items;
}

class _FakeDesignRepository implements DesignRepository {
  _FakeDesignRepository(this.items);

  final List<Design> items;

  @override
  Future<List<Design>> getAll({int? customerId}) async => customerId == null
      ? items
      : items.where((d) => d.customerId == customerId).toList();

  @override
  Future<Design?> getById(int id) async =>
      items.cast<Design?>().firstWhere((d) => d?.id == id, orElse: () => null);

  @override
  Future<int> insert(Design design) async => 1;

  @override
  Future<int> update(Design design) async => 1;

  @override
  Future<int> delete(int id) async => 1;
}

class _FakeComponentRepository implements ComponentRepository {
  _FakeComponentRepository(this.items);

  final List<Component> items;

  @override
  Future<List<Component>> getAll({String? type}) async =>
      type == null ? items : items.where((c) => c.type == type).toList();

  @override
  Future<Component?> getById(int id) async =>
      items.cast<Component?>().firstWhere((c) => c?.id == id, orElse: () => null);

  @override
  Future<int> insert(Component component) async => 1;

  @override
  Future<int> update(Component component) async => 1;

  @override
  Future<int> delete(int id) async => 1;
}

class _FakeSettingsRepository implements SettingsRepository {
  _FakeSettingsRepository(this.settings);

  final AppSettings settings;

  @override
  Future<AppSettings?> getSettings() async => settings;

  @override
  Future<int> updateSettings(AppSettings value) async => 1;

  @override
  Future<void> resetSettings() async {}
}

class _FakeQuoteRepository implements QuoteRepository {
  final List<Quote> saved = <Quote>[];
  var _nextId = 1;

  @override
  Future<List<Quote>> getAll({String? status, int? customerId}) async => saved;

  @override
  Future<Quote?> getById(int id) async =>
      saved.cast<Quote?>().firstWhere((q) => q?.id == id, orElse: () => null);

  @override
  Future<int> insert(Quote quote) async {
    final stored = quote.copyWith(id: _nextId++);
    saved.add(stored);
    return stored.id!;
  }

  @override
  Future<int> update(Quote quote) async {
    final index = saved.indexWhere((q) => q.id == quote.id);
    if (index == -1) return 0;
    saved[index] = quote;
    return 1;
  }

  @override
  Future<int> delete(int id) async {
    final before = saved.length;
    saved.removeWhere((q) => q.id == id);
    return before - saved.length;
  }

  @override
  Future<List<Quote>> getByCustomerId(int customerId) async =>
      saved.where((q) => q.customerId == customerId).toList();
}

class _FakeQuoteItemRepository implements QuoteItemRepository {
  final List<QuoteItem> saved = <QuoteItem>[];

  @override
  Future<List<QuoteItem>> getByQuoteId(int quoteId) async =>
      saved.where((i) => i.quoteId == quoteId).toList();

  @override
  Future<int> insert(QuoteItem item) async {
    saved.add(item);
    return saved.length;
  }

  @override
  Future<int> update(QuoteItem item) async => 1;

  @override
  Future<int> delete(int id) async => 0;

  @override
  Future<int> deleteByQuoteId(int quoteId) async {
    final before = saved.length;
    saved.removeWhere((i) => i.quoteId == quoteId);
    return before - saved.length;
  }
}

class _FakeTermRepository implements TermRepository {
  final List<Term> saved = <Term>[];

  @override
  Future<List<Term>> getByQuoteId(int quoteId) async =>
      saved.where((t) => t.quoteId == quoteId).toList();

  @override
  Future<int> insert(Term term) async {
    saved.add(term);
    return saved.length;
  }

  @override
  Future<int> update(Term term) async => 1;

  @override
  Future<int> delete(int id) async => 0;

  @override
  Future<int> deleteByQuoteId(int quoteId) async {
    final before = saved.length;
    saved.removeWhere((t) => t.quoteId == quoteId);
    return before - saved.length;
  }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

void main() {
  final customer = Customer(
    id: 1,
    name: 'محمد عبد الرحمن',
    phone: '01000000000',
    address: 'المنيا',
    createdAt: DateTime(2026, 10, 1),
  );

  final design = Design(
    id: 11,
    customerId: 1,
    capacityKw: 5.0,
    systemType: 'on_grid',
    customerType: 'residential',
    panelCount: 20,
    stringCount: 1,
    panelsPerString: 20,
    createdAt: DateTime(2026, 10, 7),
  );

  final panel = Component(
    id: 21,
    type: 'panel',
    brand: 'Longi',
    model: 'Hi-MO 6',
    pricePerWatt: 6.8,
    powerW: 580,
    vocV: 51.2,
    createdAt: DateTime(2026, 10, 1),
  );

  final inverter = Component(
    id: 22,
    type: 'inverter',
    brand: 'Sungrow',
    model: 'SG10RT',
    price: 45000,
    powerKw: 10,
    powerHp: 13.41,
    maxDcVoltage: 1100,
    createdAt: DateTime(2026, 10, 1),
  );

  const settings = AppSettings(id: 1, companyName: 'SolarPro مصر', defaultPricePerKw: 2000);

  late _FakeQuoteRepository quoteRepo;
  late _FakeQuoteItemRepository itemRepo;
  late _FakeTermRepository termRepo;

  String designLabel() =>
      '${design.capacityKw} ك.و · ${design.panelCount} لوح · 2026/10/07';

  Finder field(String label) => find.ancestor(
        of: find.text(label).first,
        matching: find.byType(TextFormField),
      );

  /// The form's own Scrollable.
  ///
  /// Every TextFormField also owns one (restorationId "editable") - horizontal
  /// for single-line fields and vertical for `maxLines: 3` ones - so neither
  /// `find.byType(Scrollable)` nor a filter on the axis alone is unique here.
  /// Only the ListView's own Scrollable has no restorationId.
  Finder formScrollable() => find.descendant(
        of: find.byType(ListView),
        matching: find.byWidgetPredicate(
          (widget) => widget is Scrollable && widget.restorationId == null,
        ),
      );

  /// The form is one big lazily built ListView: anything below the fold simply
  /// does not exist yet, so it has to be scrolled into view first.
  ///
  /// `target` must be a plain finder: `dragUntilVisible` keeps re-evaluating it,
  /// and a `.first` finder throws instead of reporting "not found yet".
  Future<void> scrollTo(WidgetTester tester, Finder target) async {
    await tester.dragUntilVisible(
      target,
      formScrollable(),
      const Offset(0, -200),
    );
    await tester.pumpAndSettle();
  }

  Future<void> pumpForm(WidgetTester tester) async {
    quoteRepo = _FakeQuoteRepository();
    itemRepo = _FakeQuoteItemRepository();
    termRepo = _FakeTermRepository();

    await tester.pumpWidget(
      ProviderScope(
        overrides: <Override>[
          designs.customerRepositoryProvider.overrideWith(
            (ref) => _FakeCustomerRepository(<Customer>[customer]),
          ),
          designs.designRepositoryProvider.overrideWith(
            (ref) => _FakeDesignRepository(<Design>[design]),
          ),
          componentRepositoryProvider.overrideWith(
            (ref) => _FakeComponentRepository(<Component>[panel, inverter]),
          ),
          settingsRepositoryProvider.overrideWith(
            (ref) => _FakeSettingsRepository(settings),
          ),
          quoteRepositoryProvider.overrideWith((ref) => quoteRepo),
          quoteItemRepositoryProvider.overrideWith((ref) => itemRepo),
          termRepositoryProvider.overrideWith((ref) => termRepo),
        ],
        child: const MaterialApp(
          home: Directionality(
            textDirection: TextDirection.rtl,
            child: QuoteFormScreen(),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
  }

  testWidgets('the form preselects the first customer and lists its designs',
      (WidgetTester tester) async {
    await pumpForm(tester);

    expect(find.text('محمد عبد الرحمن'), findsWidgets);

    // A DropdownButtonFormField only builds its items once the menu is open,
    // so open the design dropdown before looking for the design label.
    final dropdowns = find.byType(DropdownButtonFormField<int>);
    expect(dropdowns, findsNWidgets(2));
    await tester.tap(dropdowns.at(1));
    await tester.pumpAndSettle();
    expect(find.text(designLabel()), findsWidgets);
  });

  testWidgets('the line total follows quantity x unit price',
      (WidgetTester tester) async {
    await pumpForm(tester);

    await tester.enterText(field('البيان'), 'ألواح شمسية 580W');
    await tester.enterText(field('الكمية'), '10');
    await tester.enterText(field('سعر الوحدة (ج.م)'), '1000');
    await tester.pump();

    expect(find.text('الإجمالي: 10,000.00 ج.م'), findsOneWidget);
  });

  testWidgets('saving stores the quote, its items and the computed total',
      (WidgetTester tester) async {
    await pumpForm(tester);

    // Pick the design - it is the second dropdown on the screen.
    final dropdowns = find.byType(DropdownButtonFormField<int>);
    expect(dropdowns, findsNWidgets(2));
    await tester.tap(dropdowns.at(1));
    await tester.pumpAndSettle();
    await tester.tap(find.text(designLabel()).last);
    await tester.pumpAndSettle();

    await tester.enterText(field('البيان'), 'ألواح شمسية 580W');
    await tester.enterText(field('الكمية'), '10');
    await tester.enterText(field('سعر الوحدة (ج.م)'), '100');
    await tester.pumpAndSettle();

    await tester.tap(find.text('إنشاء عرض السعر'));
    await tester.pumpAndSettle();

    expect(quoteRepo.saved, hasLength(1));
    final quote = quoteRepo.saved.single;
    expect(quote.customerId, customer.id);
    expect(quote.designId, design.id);
    expect(quote.totalPrice, 1000);
    expect(quote.status, QuoteStatus.draft.value);

    expect(itemRepo.saved, hasLength(1));
    expect(itemRepo.saved.single.quoteId, quote.id);
    expect(itemRepo.saved.single.description, 'ألواح شمسية 580W');
    expect(itemRepo.saved.single.quantity, 10);
    expect(itemRepo.saved.single.unitPrice, 100);
  });

  testWidgets('a percentage discount and tax end up in the stored total',
      (WidgetTester tester) async {
    await pumpForm(tester);

    final dropdowns = find.byType(DropdownButtonFormField<int>);
    await tester.tap(dropdowns.at(1));
    await tester.pumpAndSettle();
    await tester.tap(find.text(designLabel()).last);
    await tester.pumpAndSettle();

    await tester.enterText(field('البيان'), 'نظام كامل');
    await tester.enterText(field('الكمية'), '1');
    await tester.enterText(field('سعر الوحدة (ج.م)'), '100000');
    // The totals card lives below the fold of the lazily built ListView.
    await scrollTo(tester, find.text('الخصم %'));
    await tester.enterText(field('الخصم %'), '10');
    await scrollTo(tester, find.text('الضريبة %'));
    await tester.enterText(field('الضريبة %'), '5');
    await tester.pumpAndSettle();

    // The submit button is the very last child of the ListView.
    await scrollTo(tester, find.text('إنشاء عرض السعر'));
    await tester.tap(find.text('إنشاء عرض السعر'));
    await tester.pumpAndSettle();

    expect(quoteRepo.saved, hasLength(1));
    final quote = quoteRepo.saved.single;
    expect(quote.discount, 10);
    expect(quote.tax, 5);
    // 100000 - 10% = 90000, + 5% tax = 94500
    expect(quote.totalPrice, closeTo(94500, 1e-9));
  });

  testWidgets('saving without a design asks the user to choose one',
      (WidgetTester tester) async {
    await pumpForm(tester);

    await tester.enterText(field('البيان'), 'ألواح');
    await tester.pump();

    await tester.tap(find.text('إنشاء عرض السعر'));
    await tester.pumpAndSettle();

    expect(quoteRepo.saved, isEmpty);
    expect(find.text('اختر التصميم'), findsOneWidget);
  });

  testWidgets('default terms can be inserted with one tap',
      (WidgetTester tester) async {
    await pumpForm(tester);

    // The terms section is below the fold too.
    await scrollTo(tester, find.text('الشروط الافتراضية'));
    await tester.tap(find.text('الشروط الافتراضية'));
    await tester.pumpAndSettle();

    // Read the fields themselves: `find.text` would depend on how the
    // EditableText renders, the controllers are what actually hold the terms.
    final typed = tester
        .widgetList<EditableText>(find.byType(EditableText))
        .map((editable) => editable.controller.text)
        .toList();
    for (final term in kDefaultTerms) {
      expect(typed, contains(term), reason: 'missing default term: $term');
    }
  });
}
