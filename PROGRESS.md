# SolarPro - Project Progress

## Project Overview
- **Name:** SolarPro
- **Description:** Solar Energy Project Management Application - manages solar projects from client intake to execution and profit tracking.

## Tech Stack
- **Framework:** Flutter (latest stable)
- **State Management:** Riverpod 3
- **Database:** sqflite (mobile) + sqflite_common_ffi (desktop) + sqflite_common_ffi_web (web)
- **Cloud Sync:** Firebase (optional, offline-first)
- **PDF Generation:** pdf package with Amiri font (Arabic support)
- **Word Generation:** Custom OOXML builder using archive package
- **GPS:** geolocator
- **HTTP:** dio
- **RTL Support:** Arabic RTL (right-to-left)

## Architecture
- Clean Architecture: data / domain / presentation
- Feature-based folder structure
- Repository pattern
- Offline-first design

## Completed Phases

### ✅ Phase 1: Foundation (COMPLETED)
- [x] Flutter project created with multi-platform support
- [x] pubspec.yaml with all dependencies configured
- [x] Folder structure created (core, features, shared)
- [x] Base files implemented:
  - lib/main.dart (MaterialApp, RTL, Material 3, themes, splash screen)
  - lib/core/constants/app_constants.dart
  - lib/core/errors/app_exception.dart
  - lib/core/theme/app_theme.dart (light/dark themes)
  - lib/core/utils/solar_calculator.dart (method stubs)
- [x] flutter pub get executed successfully
- [x] flutter analyze passes with no issues

### ✅ Phase 2: Database & Models (COMPLETED)
- [x] Database helper created (lib/core/database/database_helper.dart)
- [x] Singleton pattern with multi-platform support
- [x] All tables created with proper schema and foreign keys
- [x] CRUD operations for all entities
- [x] Customer model with toJson/fromJson/toMap/fromMap/copyWith
- [x] Design model with toJson/fromJson/toMap/fromMap/copyWith
- [x] Component model with toJson/fromJson/toMap/fromMap/copyWith
- [x] Quote model with toJson/fromJson/toMap/fromMap/copyWith
- [x] QuoteItem model with toJson/fromJson/toMap/fromMap/copyWith
- [x] Term model with toJson/fromJson/toMap/fromMap/copyWith
- [x] Project model with toJson/fromJson/toMap/fromMap/copyWith
- [x] Purchase model with toJson/fromJson/toMap/fromMap/copyWith
- [x] AppSettings model with toJson/fromJson/toMap/fromMap/copyWith
- [x] Empty repository interfaces created for all features
- [x] flutter analyze passes with no issues

### ✅ Phase 3: Repository Implementations + Solar Calculator (COMPLETED)
- [x] CustomerRepositoryImpl implemented
- [x] DesignRepositoryImpl implemented
- [x] ComponentRepositoryImpl implemented
- [x] QuoteRepositoryImpl implemented
- [x] QuoteItemRepositoryImpl implemented
- [x] TermRepositoryImpl implemented
- [x] ProjectRepositoryImpl implemented
- [x] PurchaseRepositoryImpl implemented
- [x] SettingsRepositoryImpl implemented
- [x] All repositories use DatabaseHelper with error handling
- [x] SolarCalculator fully implemented with all methods:
  - hpToKw / kwToHp conversion
  - calculateTotalPanels
  - calculateMaxPanelsPerString
  - calculateNumberOfStrings
  - distributePanelsInStrings
  - calculateSellPrice
  - calculateActualCost
  - calculateProfit
  - calculateDailyConsumption
  - suggestCapacityKw
- [x] All methods include doc comments
- [x] flutter analyze passes with no issues

## Pending Phases

### ✅ Phase 4: Presentation Layer - Customers (COMPLETED)
- [x] Customer list screen (customers_list_screen.dart)
- [x] Customer detail screen (customer_details_screen.dart)
- [x] Add/Edit customer form (customer_form_screen.dart)
- [x] Customer search and filter
- [x] Riverpod providers (customer_providers.dart)
- [x] Egypt governorates constants (egypt_governorates.dart)
- [x] main.dart rewritten — app now launches directly into CustomersListScreen
- [x] All deprecation warnings resolved (desiredAccuracy → LocationSettings, value → initialValue)
- [x] Unused import removed from customer_list_item.dart
- [x] **Bug fix**: Edit button in customer_details_screen was a no-op — now navigates to CustomerFormScreen with customer pre-filled
- [x] **Bug fix**: After editing, customerByIdProvider is invalidated so details screen refreshes
- [x] **Bug fix**: initState in form — governorate no longer falls back to first item when governorateId is null
- [x] **Bug fix**: Coordinate fields now visible in edit mode when customer already has GPS data
- [x] **Bug fix**: Delete confirmation dialog improved with clearer Arabic warning text
- [x] flutter analyze: No issues found (0 errors, 0 warnings)

### ✅ Phase 5A: Component Management (COMPLETED)
- [x] component_providers.dart — panelsListProvider, invertersListProvider, componentByIdProvider
- [x] components_list_screen.dart — TabBar (ألواح / إنفرترات), tap to edit, swipe-to-delete with Arabic confirmation
- [x] component_form_screen.dart — type selector, conditional fields, kW↔HP auto-conversion, validation, create + edit
- [x] home_screen.dart — BottomNavigationBar with 3 tabs: العملاء / المكونات / الإعدادات (placeholder)
- [x] main.dart updated — home: HomeScreen()
- [x] flutter analyze: No issues found (0 errors, 0 warnings)

### ✅ Phase 5B: Panel Pricing Fix + Design Screen (COMPLETED)
- [x] Component model updated with pricePerWatt field for panels
- [x] Database schema updated (version 2) with price_per_watt column
- [x] Component form updated to show pricePerWatt for panels / price for inverters
- [x] Component list updated to display appropriate price field per type
- [x] design_providers.dart — designRepositoryProvider, designsListProvider, designByIdProvider, customersForDropdownProvider
- [x] designs_list_screen.dart — list of designs with FAB, tap to edit, delete with confirmation
- [x] design_form_screen.dart — full design form with:
  - Basic info section (customer, capacity, system type, customer type)
  - Components section (inverter + panel dropdowns)
  - Auto-calculated section (total panels, max per string, number of strings, distribution)
  - Manual override section with reset button
  - Financial summary section (panel cost, inverter cost, total)
- [x] home_screen.dart updated with 4th tab: التصميمات
- [x] flutter analyze: 0 errors, 8 info warnings (deprecated value property)

### ✅ Phase 6: Presentation Layer - Quotes (COMPLETED)
- [x] `QuoteItem` model gained `unitPrice` + `unit` (line total = quantity × unit price)
- [x] Database schema v4 + idempotent migration (`unitPrice REAL DEFAULT 0`, `unit TEXT DEFAULT 'وحدة'`)
- [x] `AppConstants.databaseVersion` synced with `DatabaseHelper` (bug: it was stuck at 1)
- [x] `lib/features/quotes/domain/quote_totals.dart` — pure totalling logic (subtotal → discount% → tax%)
- [x] `quote_providers.dart` — `QuotesNotifier` with `saveQuote` / `updateStatus` / `deleteQuote` / `convertToProject`,
      plus `quoteByIdProvider`, `quoteItemsProvider`, `quoteTermsProvider`,
      `designsForCustomerProvider`, `projectForQuoteProvider`
- [x] `quotes_list_screen.dart` — search + status filter chips, edit/delete, FAB
- [x] `quote_form_screen.dart` — customer → design, dynamic items editor, terms editor,
      "fill from design" (panels + inverter + labour from `AppSettings.defaultPricePerKw`),
      discount/tax, live totals, create + edit
- [x] `quote_details_screen.dart` — parties, system summary, items, totals, terms,
      status menu, PDF share/print, **convert quote → project**
- [x] `quote_status_badge.dart` — Arabic labels, colours and icons for the 5 statuses
- [x] Home screen: new **عروض الأسعار** tab
- [x] Arabic PDF: `core/utils/arabic_text.dart` (Unicode-derived contextual shaper incl. LAM-ALEF
      ligature) + `core/pdf/quote_pdf.dart` + Amiri fonts bundled in `assets/fonts/`
- [x] Tests: `solar_calculator_test`, `arabic_text_test`, `currency_formatter_test`,
      `quote_pdf_test`, `quote_totals_test`, `database_quote_test`, `quote_form_screen_test`
- [x] **Bug fix**: `test/widget_test.dart` was testing a splash screen that no longer exists —
      rewritten as a real home-screen smoke test

## Pending Phases

### ⏳ Phase 7: Presentation Layer - Projects
- [ ] Project list screen
- [ ] Project detail screen
- [ ] Project progress tracking
- [ ] Installation management

### ⏳ Phase 8: Presentation Layer - Reports
- [ ] Report list screen
- [ ] Profit/loss reports
- [ ] PDF/OOXML report generation
- [ ] Export functionality

### ⏳ Phase 9: Presentation Layer - Settings & Auth
- [ ] Settings screen (theme, language, units)
- [ ] Authentication screens (login, register)
- [ ] Firebase integration (optional)

### ⏳ Phase 10: Testing & Polish
- [ ] Unit tests for utilities and calculations
- [ ] Widget tests for key screens
- [ ] Integration tests
- [ ] Performance optimization
- [ ] App store preparation

## Notes for Next Session
- Phase 6 complete: quotes can be created, edited, printed to an Arabic PDF and converted to projects.
- Bottom navigation is now: العملاء / المكونات / التصميمات / عروض الأسعار / الإعدادات
- **Arabic in PDFs**: the `pdf` package has no contextual analyser, so `ArabicText.reshape()`
  pre-shapes text into Arabic Presentation Forms before drawing. Any new PDF must use
  `_text()` from `quote_pdf.dart` (or call `ArabicText.reshape` itself), otherwise the words
  come out as detached letters.
- **Currency/percent convention**: `Quote.discount` and `Quote.tax` are percentages
  (0-100), the discount is applied before the tax, and `Quote.totalPrice` always stores the
  value computed by `QuoteTotals.compute` — never type a total by hand.
- Verification status: the sandbox this was written in has no Flutter SDK (all Google
  download hosts are blocked), so `flutter analyze` / `flutter test` were **not** executed
  here. Run them locally (or in CI) before releasing; the added tests cover the calculator,
  the Arabic shaper, the currency formatter, quote totals, the SQLite round-trip + v4
  migration, PDF generation and the quote form widget.

---

## Audit & test-fixing pass (branch `arena/00a14152-solar-pro`)

First real `flutter analyze` + `flutter test` run on this branch (70 tests):
`flutter analyze --no-fatal-infos` → **No issues found!**, `flutter test` → **57 passed / 13 failed**.
The 13 failures were triaged and fixed one by one; they were *real* bugs, not bad luck.

### Real app bug found by the widget tests
- **`quote_form_screen.dart` — the form never settled.** The customer list is read from
  SQLite, so it arrives *after* the first frame, but the first customer was preselected from a
  single `addPostFrameCallback` in `initState()`. When it fired too early no customer was ever
  selected, and the design section below it rendered `AsyncValue.loading()` → an endless
  `LinearProgressIndicator` → `pumpAndSettle` timed out (6 tests). Fixed by
  `ref.listen`-ing the customer provider (reactive preselect) and by showing a hint
  (`اختر العميل لعرض تصميماته.`) instead of a spinner while nothing is selected.

### Audit findings fixed
- **Two independent `customerRepositoryProvider`s** (one in `customer_providers.dart`, one in
  `design_providers.dart`). Overriding one in a test never affected the screens that read the
  other. `design_providers.dart` now imports *and* re-exports the shared one, so every
  importer keeps compiling and there is a single instance.
- **Dead file** `features/customers/presentation/screens/customer_list_item.dart` (empty,
  unreferenced) — deleted.
- **Currency constants lied**: `AppConstants.defaultCurrency`/`currencySymbol` said
  `SAR` / `ر.س` while the whole app prices in `ج.م`. Now `EGP` / `ج.م` (nothing read them).
- **Raw `DateTime` in a user-facing string**: the delete-confirmation dialog in
  `designs_list_screen.dart` printed `design.createdAt.toLocal()`; it now uses the same
  `_formatDate()` helper as the list tile.

### Test fixes (the assumptions were wrong, the app was right)
- `widget_test.dart`: tab labels are matched *inside* the `NavigationBar` now — `العملاء` is
  both a tab label and the customers AppBar title, so the flat `find.text` matched 2 widgets.
  The RTL check reads `Directionality.of(...)` from the home screen instead of picking the
  outermost `Directionality`, which is the ltr one `MaterialApp` installs.
- `database_quote_test.dart` / `component_design_save_test.dart`: every in-memory database is
  opened with `singleInstance: false`. sqflite caches databases by path, so a migration test
  that opens `:memory:` right after `setUp` got the *same* (already created) database and the
  `CREATE TABLE` failed with "table ... already exists".
- `component_design_save_test.dart`: `scrollUntilVisible` now gets an explicit
  `scrollable:` finder — the default one searches the whole tree, and the caller screen stays
  mounted under a pushed route, so it matched more than one `Scrollable` ("Too many elements").
  The design-form test uses `dragUntilVisible` and scrolls the save button into view before
  asserting: that button is the last child of a lazily built `ListView`, so it does not exist
  until the form is scrolled.
