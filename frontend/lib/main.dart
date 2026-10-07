import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:intl/date_symbol_data_local.dart';

import 'app.dart';
import 'core/providers.dart';
import 'core/storage/session_store.dart';
import 'features/auth/state/auth_controller.dart';

/// Entry point.
///
/// The stored session is restored before the first frame so a signed-in user
/// lands straight on the dashboard instead of seeing the login screen flash.
Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  // Arabic/English month and weekday names for every date column.
  await initializeDateFormatting();
  final SessionStore store = await SessionStore.open();
  final ProviderContainer container = ProviderContainer(
    overrides: <Override>[sessionStoreProvider.overrideWithValue(store)],
  );
  await container.read(authProvider.notifier).bootstrap();
  runApp(
    UncontrolledProviderScope(
      container: container,
      child: const KayanApp(),
    ),
  );
}
