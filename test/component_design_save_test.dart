import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart' hide DatabaseException;

import 'package:solar_pro/core/database/database_helper.dart';
import 'package:solar_pro/core/errors/app_exception.dart';
import 'package:solar_pro/features/customers/data/models/customer.dart';
import 'package:solar_pro/features/customers/data/repositories/customer_repository.dart';
import 'package:solar_pro/features/designs/data/models/component.dart';
import 'package:solar_pro/features/designs/data/models/design.dart';
import 'package:solar_pro/features/designs/data/repositories/component_repository.dart';
import 'package:solar_pro/features/designs/data/repositories/component_repository_impl.dart';
import 'package:solar_pro/features/designs/data/repositories/design_repository.dart';
import 'package:solar_pro/features/designs/data/repositories/design_repository_impl.dart';
import 'package:solar_pro/features/designs/presentation/providers/component_providers.dart';
import 'package:solar_pro/features/designs/presentation/providers/design_providers.dart';
import 'package:solar_pro/features/designs/presentation/screens/component_form_screen.dart';
import 'package:solar_pro/features/designs/presentation/screens/design_form_screen.dart';

class _FakeComponentRepository implements ComponentRepository {
  final List<Component> items = [];
  bool shouldFail = false;

  @override
  Future<List<Component>> getAll({String? type}) async {
    if (type == null) return List.unmodifiable(items);
    return items.where((c) => c.type == type).toList();
  }

  @override
  Future<Component?> getById(int id) async {
    for (final item in items) {
      if (item.id == id) return item;
    }
    return null;
  }

  @override
  Future<int> insert(Component component) async {
    if (shouldFail) {
      throw const DatabaseException('Simulated component insert failure');
    }
    final id = items.length + 1;
    items.add(component.copyWith(id: id));
    return id;
  }

  @override
  Future<int> update(Component component) async {
    if (shouldFail) {
      throw const DatabaseException('Simulated component update failure');
    }
    final index = items.indexWhere((c) => c.id == component.id);
    if (index == -1) return 0;
    items[index] = component;
    return 1;
  }

  @override
  Future<int> delete(int id) async {
    if (shouldFail) {
      throw const DatabaseException('Simulated component delete failure');
    }
    final before = items.length;
    items.removeWhere((c) => c.id == id);
    return before - items.length;
  }
}

class _FakeDesignRepository implements DesignRepository {
  final List<Design> items = [];
  bool shouldFail = false;

  @override
  Future<List<Design>> getAll({int? customerId}) async {
    if (customerId == null) return List.unmodifiable(items);
    return items.where((d) => d.customerId == customerId).toList();
  }

  @override
  Future<Design?> getById(int id) async {
    for (final item in items) {
      if (item.id == id) return item;
    }
    return null;
  }

  @override
  Future<int> insert(Design design) async {
    if (shouldFail) {
      throw const DatabaseException('Simulated design insert failure');
    }
    final id = items.length + 1;
    items.add(design.copyWith(id: id));
    return id;
  }

  @override
  Future<int> update(Design design) async {
    if (shouldFail) {
      throw const DatabaseException('Simulated design update failure');
    }
    final index = items.indexWhere((d) => d.id == design.id);
    if (index == -1) return 0;
    items[index] = design;
    return 1;
  }

  @override
  Future<int> delete(int id) async {
    if (shouldFail) {
      throw const DatabaseException('Simulated design delete failure');
    }
    final before = items.length;
    items.removeWhere((d) => d.id == id);
    return before - items.length;
  }
}

class _FakeCustomerRepository implements CustomerRepository {
  final List<Customer> items;

  _FakeCustomerRepository(this.items);

  @override
  Future<List<Customer>> getAll() async => items;

  @override
  Future<Customer?> getById(int id) async {
    for (final c in items) {
      if (c.id == id) return c;
    }
    return null;
  }

  @override
  Future<int> insert(Customer customer) async => 1;

  @override
  Future<int> update(Customer customer) async => 1;

  @override
  Future<int> delete(int id) async => 1;

  @override
  Future<List<Customer>> search(String query) async => items;
}

Finder _listViewScrollable() => find
    .descendant(
      of: find.byType(ListView),
      matching: find.byType(Scrollable),
    )
    .first;

void main() {
  group('Component price_per_watt mapping', () {
    test('toMap writes price_per_watt and fromMap reads both snake_case and camelCase', () {
      final createdAt = DateTime.utc(2026, 10, 3, 12, 0);
      final panel = Component(
        id: 7,
        type: ComponentType.panel.value,
        brand: 'JA Solar',
        model: 'JAM72S30-550/MR',
        pricePerWatt: 7.25,
        powerW: 550,
        vocV: 49.9,
        createdAt: createdAt,
      );

      final map = panel.toMap();
      expect(map.containsKey('price_per_watt'), isTrue);
      expect(map.containsKey('pricePerWatt'), isFalse);
      expect(map['price_per_watt'], 7.25);

      final roundTripped = Component.fromMap(map);
      expect(roundTripped, equals(panel));
      expect(roundTripped.pricePerWatt, 7.25);

      // Backward compatibility for maps using camelCase key
      final legacyMap = Map<String, dynamic>.from(map)
        ..remove('price_per_watt')
        ..['pricePerWatt'] = 8.5;
      final fromLegacy = Component.fromMap(legacyMap);
      expect(fromLegacy.pricePerWatt, 8.5);
    });
  });

  group('Platform database initialization', () {
    test('shouldUseDesktopFfi is true only on Linux, Windows, and macOS when not web', () {
      expect(
        DatabaseHelper.shouldUseDesktopFfi(
          isWeb: false,
          platform: TargetPlatform.linux,
        ),
        isTrue,
      );
      expect(
        DatabaseHelper.shouldUseDesktopFfi(
          isWeb: false,
          platform: TargetPlatform.windows,
        ),
        isTrue,
      );
      expect(
        DatabaseHelper.shouldUseDesktopFfi(
          isWeb: false,
          platform: TargetPlatform.macOS,
        ),
        isTrue,
      );
      expect(
        DatabaseHelper.shouldUseDesktopFfi(
          isWeb: false,
          platform: TargetPlatform.android,
        ),
        isFalse,
      );
      expect(
        DatabaseHelper.shouldUseDesktopFfi(
          isWeb: false,
          platform: TargetPlatform.iOS,
        ),
        isFalse,
      );
      expect(
        DatabaseHelper.shouldUseDesktopFfi(
          isWeb: true,
          platform: TargetPlatform.linux,
        ),
        isFalse,
      );
    });

    test('configureDatabaseFactory does not invoke FFI init on Android or iOS', () {
      var ffiInitialized = false;
      DatabaseHelper.configureDatabaseFactory(
        isWeb: false,
        platform: TargetPlatform.android,
        ffiInit: () => ffiInitialized = true,
      );
      expect(ffiInitialized, isFalse);

      DatabaseHelper.configureDatabaseFactory(
        isWeb: false,
        platform: TargetPlatform.iOS,
        ffiInit: () => ffiInitialized = true,
      );
      expect(ffiInitialized, isFalse);

      DatabaseHelper.configureDatabaseFactory(
        isWeb: false,
        platform: TargetPlatform.linux,
        ffiInit: () => ffiInitialized = true,
      );
      expect(ffiInitialized, isTrue);
    });
  });

  group('SQLite DatabaseHelper + Repository integration (in-memory FFI)', () {
    late Database db;
    late ComponentRepositoryImpl componentRepo;
    late DesignRepositoryImpl designRepo;

    setUp(() async {
      sqfliteFfiInit();
      databaseFactory = databaseFactoryFfi;
      db = await databaseFactoryFfi.openDatabase(
        inMemoryDatabasePath,
        options: OpenDatabaseOptions(
          version: 3,
          onConfigure: (d) async => d.execute('PRAGMA foreign_keys = ON'),
          onCreate: (d, _) async => DatabaseHelper.instance.createTablesForTest(d),
        ),
      );
      DatabaseHelper.setTestDatabase(db);
      componentRepo = ComponentRepositoryImpl(DatabaseHelper.instance);
      designRepo = DesignRepositoryImpl(DatabaseHelper.instance);
    });

    tearDown(() async {
      await db.close();
      DatabaseHelper.setTestDatabase(null);
    });

    test('inserts, updates, and queries panel and inverter components with price_per_watt', () async {
      final panel = Component.create(
        type: ComponentType.panel.value,
        brand: 'Longi',
        model: 'Hi-MO 6',
        pricePerWatt: 6.8,
        powerW: 580,
        vocV: 51.2,
      );
      final panelId = await componentRepo.insert(panel);
      expect(panelId, greaterThan(0));

      final inverter = Component.create(
        type: ComponentType.inverter.value,
        brand: 'Sungrow',
        model: 'SG10RT',
        price: 45000,
        powerKw: 10,
        powerHp: 13.41,
        maxDcVoltage: 1100,
      );
      final inverterId = await componentRepo.insert(inverter);
      expect(inverterId, greaterThan(0));

      final panels = await componentRepo.getAll(type: ComponentType.panel.value);
      expect(panels, hasLength(1));
      expect(panels.first.brand, 'Longi');
      expect(panels.first.pricePerWatt, 6.8);

      final updatedPanel = panels.first.copyWith(pricePerWatt: 7.1);
      final updatedRows = await componentRepo.update(updatedPanel);
      expect(updatedRows, 1);

      final fetched = await componentRepo.getById(panelId);
      expect(fetched?.pricePerWatt, 7.1);
    });

    test('inserts and updates Design preserving panelId and inverterId', () async {
      final customerId = await DatabaseHelper.instance.insertCustomer(
        Customer.create(name: 'أحمد محمد', phone: '01000000000'),
      );
      final panelId = await componentRepo.insert(
        Component.create(
          type: ComponentType.panel.value,
          brand: 'Trina',
          model: 'Vertex S+',
          pricePerWatt: 6.5,
          powerW: 500,
          vocV: 45.0,
        ),
      );
      final inverterId = await componentRepo.insert(
        Component.create(
          type: ComponentType.inverter.value,
          brand: 'Growatt',
          model: 'MIN 5000TL-X',
          price: 28000,
          powerKw: 5.0,
          powerHp: 6.7,
          maxDcVoltage: 550,
        ),
      );

      final design = Design.create(
        customerId: customerId,
        capacityKw: 5.0,
        systemType: 'on_grid',
        customerType: 'residential',
        inverterId: inverterId,
        panelId: panelId,
        panelCount: 10,
        stringCount: 1,
        panelsPerString: 10,
        notes: 'تصميم تجريبي',
      );

      final designId = await designRepo.insert(design);
      expect(designId, greaterThan(0));

      final loaded = await designRepo.getById(designId);
      expect(loaded, isNotNull);
      expect(loaded!.panelId, panelId);
      expect(loaded.inverterId, inverterId);
      expect(loaded.panelCount, 10);

      final updatedRows = await designRepo.update(
        loaded.copyWith(capacityKw: 6.0, panelCount: 12),
      );
      expect(updatedRows, 1);

      final reloaded = await designRepo.getById(designId);
      expect(reloaded?.capacityKw, 6.0);
      expect(reloaded?.panelId, panelId);
    });

    test('safe migration from v1 to v3 adds price_per_watt and panelId without losing data', () async {
      final legacyDb = await databaseFactoryFfi.openDatabase(
        inMemoryDatabasePath,
        options: OpenDatabaseOptions(singleInstance: false),
      );
      await legacyDb.execute('''
        CREATE TABLE components (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          type TEXT NOT NULL,
          brand TEXT NOT NULL,
          model TEXT NOT NULL,
          price REAL DEFAULT 0,
          powerW INTEGER,
          vocV REAL,
          powerKw REAL,
          powerHp REAL,
          maxDcVoltage REAL,
          createdAt TEXT NOT NULL
        )
      ''');
      await legacyDb.execute('''
        CREATE TABLE designs (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          customerId INTEGER NOT NULL,
          capacityKw REAL NOT NULL,
          systemType TEXT NOT NULL,
          customerType TEXT NOT NULL,
          inverterId INTEGER,
          panelCount INTEGER DEFAULT 0,
          stringCount INTEGER DEFAULT 0,
          panelsPerString INTEGER DEFAULT 0,
          notes TEXT,
          createdAt TEXT NOT NULL
        )
      ''');

      await legacyDb.insert('components', {
        'id': 1,
        'type': 'panel',
        'brand': 'JA Solar',
        'model': '550W-V1',
        'price': 0,
        'powerW': 550,
        'vocV': 49.5,
        'createdAt': '2026-10-01T00:00:00.000Z',
      });
      await legacyDb.insert('designs', {
        'id': 1,
        'customerId': 1,
        'capacityKw': 5.0,
        'systemType': 'on_grid',
        'customerType': 'residential',
        'inverterId': 1,
        'panelCount': 10,
        'stringCount': 1,
        'panelsPerString': 10,
        'notes': 'تصميم قديم',
        'createdAt': '2026-10-01T00:00:00.000Z',
      });

      await DatabaseHelper.instance.upgradeDatabaseForTest(legacyDb, 1, 3);
      // Running upgrade again is idempotent
      await DatabaseHelper.instance.upgradeDatabaseForTest(legacyDb, 1, 3);

      final compCols = await legacyDb.rawQuery('PRAGMA table_info(components)');
      expect(compCols.any((c) => c['name'] == 'price_per_watt'), isTrue);

      final designCols = await legacyDb.rawQuery('PRAGMA table_info(designs)');
      expect(designCols.any((c) => c['name'] == 'panelId'), isTrue);

      final oldComponents = await legacyDb.query('components');
      expect(oldComponents, hasLength(1));
      expect(oldComponents.first['model'], '550W-V1');

      final oldDesigns = await legacyDb.query('designs');
      expect(oldDesigns, hasLength(1));
      expect(oldDesigns.first['notes'], 'تصميم قديم');

      await legacyDb.close();
    });
  });

  group('ComponentFormScreen widget save and error flows', () {
    testWidgets('saves a new panel component and pops the form screen', (tester) async {
      final fakeRepo = _FakeComponentRepository();

      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            componentRepositoryProvider.overrideWithValue(fakeRepo),
          ],
          child: MaterialApp(
            home: Builder(
              builder: (context) => Scaffold(
                body: Center(
                  child: ElevatedButton(
                    onPressed: () {
                      Navigator.of(context).push(
                        MaterialPageRoute(
                          builder: (_) => const ComponentFormScreen(),
                        ),
                      );
                    },
                    child: const Text('Open Form'),
                  ),
                ),
              ),
            ),
          ),
        ),
      );

      await tester.tap(find.text('Open Form'));
      await tester.pumpAndSettle();

      expect(find.byType(ComponentFormScreen), findsOneWidget);

      final fields = find.byType(TextFormField);
      // 0: brand, 1: model, 2: pricePerWatt, 3: powerW, 4: vocV
      await tester.enterText(fields.at(0), 'Jinko');
      await tester.enterText(fields.at(1), 'Tiger Neo');
      await tester.enterText(fields.at(2), '7.5');
      await tester.enterText(fields.at(3), '550');
      await tester.enterText(fields.at(4), '49.8');

      final saveButton = find.widgetWithText(FilledButton, 'حفظ المكوّن');
      await tester.scrollUntilVisible(
        saveButton,
        200,
        scrollable: _listViewScrollable(),
      );
      await tester.tap(saveButton);
      await tester.pumpAndSettle();

      expect(fakeRepo.items, hasLength(1));
      expect(fakeRepo.items.first.brand, 'Jinko');
      expect(fakeRepo.items.first.pricePerWatt, 7.5);
      expect(find.byType(ComponentFormScreen), findsNothing);
    });

    testWidgets('keeps ComponentFormScreen open and shows error SnackBar when save fails', (tester) async {
      final fakeRepo = _FakeComponentRepository()..shouldFail = true;

      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            componentRepositoryProvider.overrideWithValue(fakeRepo),
          ],
          child: const MaterialApp(
            home: ComponentFormScreen(),
          ),
        ),
      );

      final fields = find.byType(TextFormField);
      await tester.enterText(fields.at(0), 'Jinko');
      await tester.enterText(fields.at(1), 'Tiger Neo');
      await tester.enterText(fields.at(2), '7.5');
      await tester.enterText(fields.at(3), '550');
      await tester.enterText(fields.at(4), '49.8');

      final saveButton = find.widgetWithText(FilledButton, 'حفظ المكوّن');
      await tester.scrollUntilVisible(
        saveButton,
        200,
        scrollable: _listViewScrollable(),
      );
      await tester.tap(saveButton);
      await tester.pumpAndSettle();

      // Screen must remain open and display the error message
      expect(find.byType(ComponentFormScreen), findsOneWidget);
      expect(find.textContaining('فشل الحفظ'), findsOneWidget);
    });
  });

  group('DesignFormScreen widget rebuild and save flows', () {
    testWidgets('settles without infinite post-frame rebuild loop and edits/saves Design', (tester) async {
      final fakeComponentRepo = _FakeComponentRepository()
        ..items.addAll([
          Component(
            id: 1,
            type: ComponentType.panel.value,
            brand: 'JA Solar',
            model: '550W',
            pricePerWatt: 7.0,
            powerW: 550,
            vocV: 49.5,
            createdAt: DateTime(2026, 10, 3),
          ),
          Component(
            id: 2,
            type: ComponentType.inverter.value,
            brand: 'Huawei',
            model: 'SUN2000-5KTL',
            price: 30000,
            powerKw: 5.0,
            powerHp: 6.7,
            maxDcVoltage: 600,
            createdAt: DateTime(2026, 10, 3),
          ),
        ]);
      final fakeDesignRepo = _FakeDesignRepository();
      final existingDesign = Design(
        id: 10,
        customerId: 1,
        capacityKw: 5.5,
        systemType: 'on_grid',
        customerType: 'residential',
        inverterId: 2,
        panelId: 1,
        panelCount: 10,
        stringCount: 1,
        panelsPerString: 10,
        createdAt: DateTime(2026, 10, 3),
      );
      fakeDesignRepo.items.add(existingDesign);

      final fakeCustomerRepo = _FakeCustomerRepository([
        Customer(id: 1, name: 'عميل تجريبي', createdAt: DateTime(2026, 10, 3)),
      ]);

      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            componentRepositoryProvider.overrideWithValue(fakeComponentRepo),
            designRepositoryProvider.overrideWithValue(fakeDesignRepo),
            customerRepositoryProvider.overrideWithValue(fakeCustomerRepo),
          ],
          child: MaterialApp(
            home: DesignFormScreen(design: existingDesign),
          ),
        ),
      );

      // Should settle cleanly without timing out from an infinite post-frame loop
      await tester.pumpAndSettle();

      expect(find.byType(DesignFormScreen), findsOneWidget);
      expect(find.text('تعديل التصميم'), findsOneWidget);

      final updateButton = find.widgetWithText(FilledButton, 'تحديث');
      await tester.scrollUntilVisible(
        updateButton,
        200,
        scrollable: _listViewScrollable(),
      );
      expect(updateButton, findsOneWidget);
      await tester.tap(updateButton);
      await tester.pumpAndSettle();

      expect(fakeDesignRepo.items.first.panelId, 1);
      expect(fakeDesignRepo.items.first.inverterId, 2);
    });
  });
}
