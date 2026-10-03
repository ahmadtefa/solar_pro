import 'package:flutter/foundation.dart';
import 'package:path/path.dart';
import 'package:path_provider/path_provider.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';
import 'package:sqflite_common_ffi_web/sqflite_ffi_web.dart';

import '../../features/customers/data/models/customer.dart';
import '../../features/designs/data/models/design.dart';
import '../../features/designs/data/models/component.dart';
import '../../features/quotes/data/models/quote.dart';
import '../../features/quotes/data/models/quote_item.dart';
import '../../features/quotes/data/models/term.dart';
import '../../features/projects/data/models/project.dart';
import '../../features/projects/data/models/purchase.dart';
import '../../features/settings/data/models/app_settings.dart';

class DatabaseHelper {
  static DatabaseHelper? _instance;
  static Database? _database;

  DatabaseHelper._();

  static DatabaseHelper get instance {
    _instance ??= DatabaseHelper._();
    return _instance!;
  }

  /// Returns true only on desktop platforms (Linux, Windows, macOS) when not running on Web.
  static bool shouldUseDesktopFfi({
    bool isWeb = kIsWeb,
    TargetPlatform? platform,
  }) {
    if (isWeb) return false;
    final target = platform ?? defaultTargetPlatform;
    return target == TargetPlatform.linux ||
        target == TargetPlatform.windows ||
        target == TargetPlatform.macOS;
  }

  /// Configures the sqflite [databaseFactory] for the current platform.
  /// Desktop platforms use `sqflite_common_ffi`, Web uses `sqflite_common_ffi_web`,
  /// and mobile platforms (Android/iOS) keep the default native `sqflite` plugin.
  static void configureDatabaseFactory({
    bool isWeb = kIsWeb,
    TargetPlatform? platform,
    void Function()? ffiInit,
  }) {
    if (isWeb) {
      databaseFactory = databaseFactoryFfiWeb;
      return;
    }
    if (shouldUseDesktopFfi(isWeb: isWeb, platform: platform)) {
      (ffiInit ?? sqfliteFfiInit)();
      databaseFactory = databaseFactoryFfi;
    }
  }

  @visibleForTesting
  static void setTestDatabase(Database? db) {
    _database = db;
  }

  @visibleForTesting
  Future<void> createTablesForTest(Database db) => _createTables(db);

  @visibleForTesting
  Future<void> upgradeDatabaseForTest(
    Database db,
    int oldVersion,
    int newVersion,
  ) => _onUpgrade(db, oldVersion, newVersion);

  Future<Database> get database async {
    _database ??= await _initDatabase();
    return _database!;
  }

  Future<Database> _initDatabase() async {
    configureDatabaseFactory();

    final String path;
    if (kIsWeb) {
      path = 'solar_pro.db';
    } else {
      final documentsDirectory = await getApplicationDocumentsDirectory();
      path = join(documentsDirectory.path, 'solar_pro.db');
    }

    return await openDatabase(
      path,
      version: 3,
      onCreate: _onCreate,
      onUpgrade: _onUpgrade,
      onConfigure: (db) async {
        await db.execute('PRAGMA foreign_keys = ON');
      },
    );
  }

  Future<void> _onCreate(Database db, int version) async {
    await _createTables(db);
  }

  Future<bool> _hasColumn(Database db, String table, String column) async {
    final columns = await db.rawQuery('PRAGMA table_info($table)');
    return columns.any((col) => col['name'] == column);
  }

  Future<void> _onUpgrade(Database db, int oldVersion, int newVersion) async {
    // Handle migrations here for future versions
    if (oldVersion < 2) {
      // Add price_per_watt column to components table
      if (!await _hasColumn(db, 'components', 'price_per_watt')) {
        await db.execute(
          'ALTER TABLE components ADD COLUMN price_per_watt REAL',
        );
      }
    }
    if (oldVersion < 3) {
      // Add nullable panelId column to designs table for editing support
      if (!await _hasColumn(db, 'designs', 'panelId')) {
        await db.execute(
          'ALTER TABLE designs ADD COLUMN panelId INTEGER REFERENCES components(id) ON DELETE SET NULL',
        );
      }
    }
  }

  Future<void> _createTables(Database db) async {
    // Customers table
    await db.execute('''
      CREATE TABLE customers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        phone TEXT,
        address TEXT,
        locationMethod TEXT DEFAULT 'manual',
        governorateId INTEGER,
        cityId INTEGER,
        latitude REAL,
        longitude REAL,
        pshUsed INTEGER DEFAULT 0,
        createdAt TEXT NOT NULL
      )
    ''');

    // Components table
    await db.execute('''
      CREATE TABLE components (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        type TEXT NOT NULL,
        brand TEXT NOT NULL,
        model TEXT NOT NULL,
        price REAL DEFAULT 0,
        price_per_watt REAL,
        powerW INTEGER,
        vocV REAL,
        powerKw REAL,
        powerHp REAL,
        maxDcVoltage REAL,
        createdAt TEXT NOT NULL
      )
    ''');

    // Designs table
    await db.execute('''
      CREATE TABLE designs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        customerId INTEGER NOT NULL,
        capacityKw REAL NOT NULL,
        systemType TEXT NOT NULL,
        customerType TEXT NOT NULL,
        inverterId INTEGER,
        panelId INTEGER,
        panelCount INTEGER DEFAULT 0,
        stringCount INTEGER DEFAULT 0,
        panelsPerString INTEGER DEFAULT 0,
        notes TEXT,
        createdAt TEXT NOT NULL,
        FOREIGN KEY (customerId) REFERENCES customers(id) ON DELETE CASCADE,
        FOREIGN KEY (inverterId) REFERENCES components(id) ON DELETE SET NULL,
        FOREIGN KEY (panelId) REFERENCES components(id) ON DELETE SET NULL
      )
    ''');

    // Quotes table
    await db.execute('''
      CREATE TABLE quotes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        designId INTEGER NOT NULL,
        customerId INTEGER NOT NULL,
        totalPrice REAL DEFAULT 0,
        discount REAL DEFAULT 0,
        tax REAL DEFAULT 0,
        status TEXT DEFAULT 'draft',
        createdAt TEXT NOT NULL,
        FOREIGN KEY (designId) REFERENCES designs(id) ON DELETE CASCADE,
        FOREIGN KEY (customerId) REFERENCES customers(id) ON DELETE CASCADE
      )
    ''');

    // Quote items table
    await db.execute('''
      CREATE TABLE quote_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        quoteId INTEGER NOT NULL,
        description TEXT NOT NULL,
        quantity INTEGER DEFAULT 1,
        originCountry TEXT,
        warranty TEXT,
        orderIndex INTEGER DEFAULT 0,
        FOREIGN KEY (quoteId) REFERENCES quotes(id) ON DELETE CASCADE
      )
    ''');

    // Terms table
    await db.execute('''
      CREATE TABLE terms (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        quoteId INTEGER NOT NULL,
        text TEXT NOT NULL,
        orderIndex INTEGER DEFAULT 0,
        FOREIGN KEY (quoteId) REFERENCES quotes(id) ON DELETE CASCADE
      )
    ''');

    // Projects table
    await db.execute('''
      CREATE TABLE projects (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        quoteId INTEGER NOT NULL UNIQUE,
        status TEXT DEFAULT 'pending',
        startDate TEXT,
        endDate TEXT,
        progressPercent REAL DEFAULT 0,
        createdAt TEXT NOT NULL,
        FOREIGN KEY (quoteId) REFERENCES quotes(id) ON DELETE CASCADE
      )
    ''');

    // Purchases table
    await db.execute('''
      CREATE TABLE purchases (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        projectId INTEGER NOT NULL,
        itemName TEXT NOT NULL,
        price REAL DEFAULT 0,
        supplier TEXT,
        type TEXT DEFAULT 'component',
        purchaseDate TEXT,
        createdAt TEXT NOT NULL,
        FOREIGN KEY (projectId) REFERENCES projects(id) ON DELETE CASCADE
      )
    ''');

    // App settings table (singleton)
    await db.execute('''
      CREATE TABLE app_settings (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        companyName TEXT,
        companyPhone TEXT,
        companyLogoPath TEXT,
        defaultPricePerKw REAL DEFAULT 0,
        defaultPsh REAL DEFAULT 5.0
      )
    ''');

    // Insert default settings
    await db.insert('app_settings', {
      'id': 1,
      'companyName': '',
      'companyPhone': '',
      'companyLogoPath': '',
      'defaultPricePerKw': 0,
      'defaultPsh': 5.0,
    });

    // Create indexes for better query performance
    await db.execute('CREATE INDEX idx_customers_name ON customers(name)');
    await db.execute('CREATE INDEX idx_designs_customerId ON designs(customerId)');
    await db.execute('CREATE INDEX idx_quotes_designId ON quotes(designId)');
    await db.execute('CREATE INDEX idx_quotes_customerId ON quotes(customerId)');
    await db.execute('CREATE INDEX idx_projects_quoteId ON projects(quoteId)');
    await db.execute('CREATE INDEX idx_purchases_projectId ON purchases(projectId)');
  }

  // Generic CRUD operations
  Future<int> insert<T>(String table, Map<String, dynamic> data) async {
    final db = await database;
    return await db.insert(table, data, conflictAlgorithm: ConflictAlgorithm.replace);
  }

  Future<List<Map<String, dynamic>>> query(
    String table, {
    String? where,
    List<Object?>? whereArgs,
    String? orderBy,
    int? limit,
  }) async {
    final db = await database;
    return await db.query(
      table,
      where: where,
      whereArgs: whereArgs,
      orderBy: orderBy,
      limit: limit,
    );
  }

  Future<int> update(
    String table,
    Map<String, dynamic> data, {
    String? where,
    List<Object?>? whereArgs,
  }) async {
    final db = await database;
    return await db.update(table, data, where: where, whereArgs: whereArgs);
  }

  Future<int> delete(
    String table, {
    String? where,
    List<Object?>? whereArgs,
  }) async {
    final db = await database;
    return await db.delete(table, where: where, whereArgs: whereArgs);
  }

  Future<void> rawQuery(String sql, [List<Object?>? arguments]) async {
    final db = await database;
    await db.rawQuery(sql, arguments);
  }

  Future<List<Map<String, dynamic>>> rawQueryList(
    String sql, [List<Object?>? arguments]) async {
    final db = await database;
    return await db.rawQuery(sql, arguments);
  }

  Future<void> close() async {
    final db = await database;
    await db.close();
    _database = null;
  }

  // Table-specific helper methods for models
  Future<int> insertCustomer(Customer customer) async {
    return insert('customers', customer.toMap());
  }

  Future<List<Customer>> getCustomers() async {
    final maps = await query('customers', orderBy: 'createdAt DESC');
    return maps.map((m) => Customer.fromMap(m)).toList();
  }

  Future<Customer?> getCustomer(int id) async {
    final maps = await query('customers', where: 'id = ?', whereArgs: [id]);
    if (maps.isEmpty) return null;
    return Customer.fromMap(maps.first);
  }

  Future<int> updateCustomer(Customer customer) async {
    return update('customers', customer.toMap(), where: 'id = ?', whereArgs: [customer.id]);
  }

  Future<int> deleteCustomer(int id) async {
    // Delete related records first due to foreign keys
    await rawQuery('DELETE FROM designs WHERE customerId = ?', [id]);
    await rawQuery('DELETE FROM quotes WHERE customerId = ?', [id]);
    return delete('customers', where: 'id = ?', whereArgs: [id]);
  }

  Future<int> insertComponent(Component component) async {
    return insert('components', component.toMap());
  }

  Future<List<Component>> getComponents({String? type}) async {
    if (type != null) {
      final maps = await query('components', where: 'type = ?', whereArgs: [type]);
      return maps.map((m) => Component.fromMap(m)).toList();
    }
    final maps = await query('components', orderBy: 'brand, model');
    return maps.map((m) => Component.fromMap(m)).toList();
  }

  Future<int> updateComponent(Component component) async {
    return update('components', component.toMap(), where: 'id = ?', whereArgs: [component.id]);
  }

  Future<int> deleteComponent(int id) async {
    return delete('components', where: 'id = ?', whereArgs: [id]);
  }

  Future<int> insertDesign(Design design) async {
    return insert('designs', design.toMap());
  }

  Future<List<Design>> getDesigns({int? customerId}) async {
    if (customerId != null) {
      final maps = await query('designs', where: 'customerId = ?', whereArgs: [customerId], orderBy: 'createdAt DESC');
      return maps.map((m) => Design.fromMap(m)).toList();
    }
    final maps = await query('designs', orderBy: 'createdAt DESC');
    return maps.map((m) => Design.fromMap(m)).toList();
  }

  Future<Design?> getDesign(int id) async {
    final maps = await query('designs', where: 'id = ?', whereArgs: [id]);
    if (maps.isEmpty) return null;
    return Design.fromMap(maps.first);
  }

  Future<int> updateDesign(Design design) async {
    return update('designs', design.toMap(), where: 'id = ?', whereArgs: [design.id]);
  }

  Future<int> deleteDesign(int id) async {
    return delete('designs', where: 'id = ?', whereArgs: [id]);
  }

  Future<int> insertQuote(Quote quote) async {
    return insert('quotes', quote.toMap());
  }

  Future<List<Quote>> getQuotes({String? status, int? customerId}) async {
    String? where;
    final whereArgs = <Object?>[];
    
    if (status != null) {
      where = 'status = ?';
      whereArgs.add(status);
    }
    if (customerId != null) {
      where = where == null ? 'customerId = ?' : '$where AND customerId = ?';
      whereArgs.add(customerId);
    }
    
    final maps = await query('quotes', where: where, whereArgs: whereArgs.isNotEmpty ? whereArgs : null, orderBy: 'createdAt DESC');
    return maps.map((m) => Quote.fromMap(m)).toList();
  }

  Future<Quote?> getQuote(int id) async {
    final maps = await query('quotes', where: 'id = ?', whereArgs: [id]);
    if (maps.isEmpty) return null;
    return Quote.fromMap(maps.first);
  }

  Future<int> updateQuote(Quote quote) async {
    return update('quotes', quote.toMap(), where: 'id = ?', whereArgs: [quote.id]);
  }

  Future<int> deleteQuote(int id) async {
    return delete('quotes', where: 'id = ?', whereArgs: [id]);
  }

  Future<int> insertQuoteItem(QuoteItem item) async {
    return insert('quote_items', item.toMap());
  }

  Future<List<QuoteItem>> getQuoteItems(int quoteId) async {
    final maps = await query('quote_items', where: 'quoteId = ?', whereArgs: [quoteId], orderBy: 'orderIndex');
    return maps.map((m) => QuoteItem.fromMap(m)).toList();
  }

  Future<int> updateQuoteItem(QuoteItem item) async {
    return update('quote_items', item.toMap(), where: 'id = ?', whereArgs: [item.id]);
  }

  Future<int> deleteQuoteItem(int id) async {
    return delete('quote_items', where: 'id = ?', whereArgs: [id]);
  }

  Future<int> insertTerm(Term term) async {
    return insert('terms', term.toMap());
  }

  Future<List<Term>> getTerms(int quoteId) async {
    final maps = await query('terms', where: 'quoteId = ?', whereArgs: [quoteId], orderBy: 'orderIndex');
    return maps.map((m) => Term.fromMap(m)).toList();
  }

  Future<int> updateTerm(Term term) async {
    return update('terms', term.toMap(), where: 'id = ?', whereArgs: [term.id]);
  }

  Future<int> deleteTerm(int id) async {
    return delete('terms', where: 'id = ?', whereArgs: [id]);
  }

  Future<int> insertProject(Project project) async {
    return insert('projects', project.toMap());
  }

  Future<List<Project>> getProjects({String? status}) async {
    if (status != null) {
      final maps = await query('projects', where: 'status = ?', whereArgs: [status], orderBy: 'startDate DESC');
      return maps.map((m) => Project.fromMap(m)).toList();
    }
    final maps = await query('projects', orderBy: 'startDate DESC');
    return maps.map((m) => Project.fromMap(m)).toList();
  }

  Future<Project?> getProject(int id) async {
    final maps = await query('projects', where: 'id = ?', whereArgs: [id]);
    if (maps.isEmpty) return null;
    return Project.fromMap(maps.first);
  }

  Future<int> updateProject(Project project) async {
    return update('projects', project.toMap(), where: 'id = ?', whereArgs: [project.id]);
  }

  Future<int> deleteProject(int id) async {
    return delete('projects', where: 'id = ?', whereArgs: [id]);
  }

  Future<int> insertPurchase(Purchase purchase) async {
    return insert('purchases', purchase.toMap());
  }

  Future<List<Purchase>> getPurchases(int projectId) async {
    final maps = await query('purchases', where: 'projectId = ?', whereArgs: [projectId], orderBy: 'purchaseDate DESC');
    return maps.map((m) => Purchase.fromMap(m)).toList();
  }

  Future<int> updatePurchase(Purchase purchase) async {
    return update('purchases', purchase.toMap(), where: 'id = ?', whereArgs: [purchase.id]);
  }

  Future<int> deletePurchase(int id) async {
    return delete('purchases', where: 'id = ?', whereArgs: [id]);
  }

  Future<AppSettings?> getAppSettings() async {
    final maps = await query('app_settings', where: 'id = 1');
    if (maps.isEmpty) return null;
    return AppSettings.fromMap(maps.first);
  }

  Future<int> updateAppSettings(AppSettings settings) async {
    return update('app_settings', settings.toMap(), where: 'id = 1');
  }
}
