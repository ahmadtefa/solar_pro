import 'package:flutter_test/flutter_test.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';

import 'package:solar_pro/core/database/database_helper.dart';
import 'package:solar_pro/features/customers/data/models/customer.dart';
import 'package:solar_pro/features/designs/data/models/design.dart';
import 'package:solar_pro/features/projects/data/models/project.dart';
import 'package:solar_pro/features/projects/data/repositories/project_repository_impl.dart';
import 'package:solar_pro/features/quotes/data/models/quote.dart';
import 'package:solar_pro/features/quotes/data/models/quote_item.dart';
import 'package:solar_pro/features/quotes/data/models/term.dart';
import 'package:solar_pro/features/quotes/data/repositories/quote_item_repository_impl.dart';
import 'package:solar_pro/features/quotes/data/repositories/quote_repository_impl.dart';
import 'package:solar_pro/features/quotes/data/repositories/term_repository_impl.dart';

/// `true` when the host can load SQLite through dart:ffi (Linux/macOS/Windows).
bool _ffiAvailable = false;

void main() {
  setUpAll(() {
    try {
      sqfliteFfiInit();
      databaseFactory = databaseFactoryFfi;
      _ffiAvailable = true;
    } catch (_) {
      _ffiAvailable = false;
    }
  });

  group('Quotes in SQLite (in-memory FFI)', () {
    late Database db;
    late QuoteRepositoryImpl quoteRepo;
    late QuoteItemRepositoryImpl itemRepo;
    late TermRepositoryImpl termRepo;

    setUp(() async {
      if (!_ffiAvailable) return;
      db = await databaseFactoryFfi.openDatabase(
        inMemoryDatabasePath,
        options: OpenDatabaseOptions(
          version: 4,
          onConfigure: (d) async => d.execute('PRAGMA foreign_keys = ON'),
          onCreate: (d, _) async => DatabaseHelper.instance.createTablesForTest(d),
        ),
      );
      DatabaseHelper.setTestDatabase(db);
      quoteRepo = QuoteRepositoryImpl(DatabaseHelper.instance);
      itemRepo = QuoteItemRepositoryImpl(DatabaseHelper.instance);
      termRepo = TermRepositoryImpl(DatabaseHelper.instance);
    });

    tearDown(() async {
      if (!_ffiAvailable) return;
      await db.close();
      DatabaseHelper.setTestDatabase(null);
    });

    Future<int> _seedDesign() async {
      final customerId = await DatabaseHelper.instance.insertCustomer(
        Customer.create(name: 'شركة النور', phone: '01012345678'),
      );
      return DatabaseHelper.instance.insertDesign(
        Design.create(
          customerId: customerId,
          capacityKw: 10,
          systemType: 'on_grid',
          customerType: 'commercial',
          panelCount: 18,
          stringCount: 2,
          panelsPerString: 9,
        ),
      );
    }

    test('stores a quote with its items and terms and reads them back', () async {
      if (!_ffiAvailable) return;
      final designId = await _seedDesign();
      final design = await DatabaseHelper.instance.getDesign(designId);

      final quoteId = await quoteRepo.insert(
        Quote.create(designId: designId, customerId: design!.customerId),
      );

      await itemRepo.insert(
        QuoteItem.create(
          quoteId: quoteId,
          description: 'ألواح شمسية 550W',
          quantity: 18,
          unitPrice: 5400,
          unit: 'لوح',
          originCountry: 'الصين',
          warranty: '10 سنوات',
          orderIndex: 0,
        ),
      );
      await itemRepo.insert(
        QuoteItem.create(
          quoteId: quoteId,
          description: 'إنفرتر 10kW',
          quantity: 1,
          unitPrice: 45000,
          unit: 'جهاز',
          orderIndex: 1,
        ),
      );
      await termRepo.insert(
        Term.create(quoteId: quoteId, text: 'الأسعار تشمل التركيب', orderIndex: 0),
      );

      final stored = await quoteRepo.getById(quoteId);
      expect(stored, isNotNull);
      expect(stored!.designId, designId);
      expect(stored.status, QuoteStatus.draft.value);

      final items = await itemRepo.getByQuoteId(quoteId);
      expect(items, hasLength(2));
      expect(items.first.orderIndex, 0,
          reason: 'items must come back in the saved order');
      expect(items.first.lineTotal, 5400 * 18);
      expect(items.first.unit, 'لوح');
      expect(items[1].unitPrice, 45000);

      final terms = await termRepo.getByQuoteId(quoteId);
      expect(terms.single.text, 'الأسعار تشمل التركيب');
    });

    test('updating a quote keeps its children', () async {
      if (!_ffiAvailable) return;
      final designId = await _seedDesign();
      final quoteId = await quoteRepo.insert(
        Quote.create(designId: designId, customerId: 1),
      );
      await itemRepo.insert(
        QuoteItem.create(
            quoteId: quoteId, description: 'لوح', quantity: 1, unitPrice: 100),
      );

      final stored = await quoteRepo.getById(quoteId);
      final rows = await quoteRepo.update(
        stored!.copyWith(status: QuoteStatus.sent.value, totalPrice: 100),
      );
      expect(rows, 1);

      final reloaded = await quoteRepo.getById(quoteId);
      expect(reloaded!.status, QuoteStatus.sent.value);
      expect(reloaded.totalPrice, 100);
      expect(await itemRepo.getByQuoteId(quoteId), hasLength(1));
    });

    test('deleting a quote cascades to its items and terms', () async {
      if (!_ffiAvailable) return;
      final designId = await _seedDesign();
      final quoteId = await quoteRepo.insert(
        Quote.create(designId: designId, customerId: 1),
      );
      await itemRepo.insert(
        QuoteItem.create(
            quoteId: quoteId, description: 'لوح', quantity: 1, unitPrice: 100),
      );
      await termRepo.insert(
        Term.create(quoteId: quoteId, text: 'شرط'),
      );

      await quoteRepo.delete(quoteId);

      expect(await quoteRepo.getById(quoteId), isNull);
      expect(await itemRepo.getByQuoteId(quoteId), isEmpty);
      expect(await termRepo.getByQuoteId(quoteId), isEmpty);
    });

    test('a quote can be turned into exactly one project', () async {
      if (!_ffiAvailable) return;
      final designId = await _seedDesign();
      final quoteId = await quoteRepo.insert(
        Quote.create(designId: designId, customerId: 1),
      );

      final projectRepo = ProjectRepositoryImpl(DatabaseHelper.instance);
      expect(await projectRepo.getByQuoteId(quoteId), isEmpty);

      final projectId = await projectRepo.insert(
        Project.create(quoteId: quoteId, status: ProjectStatus.pending.value),
      );
      expect(projectId, greaterThan(0));

      final projects = await projectRepo.getByQuoteId(quoteId);
      expect(projects, hasLength(1));
      expect(projects.first.status, ProjectStatus.pending.value);
      expect(projects.first.progressPercent, 0);
    });

    test('migration to v4 adds unitPrice and unit to quote_items', () async {
      if (!_ffiAvailable) return;
      final legacyDb =
          await databaseFactoryFfi.openDatabase(inMemoryDatabasePath);
      await legacyDb.execute('''
        CREATE TABLE quote_items (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          quoteId INTEGER NOT NULL,
          description TEXT NOT NULL,
          quantity INTEGER DEFAULT 1,
          originCountry TEXT,
          warranty TEXT,
          orderIndex INTEGER DEFAULT 0
        )
      ''');

      await DatabaseHelper.instance.upgradeDatabaseForTest(legacyDb, 3, 4);
      // Running it twice must stay safe.
      await DatabaseHelper.instance.upgradeDatabaseForTest(legacyDb, 3, 4);

      final columns = await legacyDb.rawQuery('PRAGMA table_info(quote_items)');
      expect(columns.any((c) => c['name'] == 'unitPrice'), isTrue);
      expect(columns.any((c) => c['name'] == 'unit'), isTrue);

      final id = await legacyDb.insert('quote_items', <String, Object?>{
        'quoteId': 1,
        'description': 'لوح قديم',
        'quantity': 2,
      });
      final row = await legacyDb
          .query('quote_items', where: 'id = ?', whereArgs: <Object?>[id]);
      final item = QuoteItem.fromMap(row.first);
      expect(item.unitPrice, 0);
      expect(item.unit, 'وحدة');

      await legacyDb.close();
    });
  });
}
