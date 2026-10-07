import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../../core/database/database_helper.dart';
import '../../data/models/app_settings.dart';
import '../../data/repositories/settings_repository.dart';
import '../../data/repositories/settings_repository_impl.dart';

final settingsRepositoryProvider = Provider<SettingsRepository>((ref) {
  return SettingsRepositoryImpl(DatabaseHelper.instance);
});

/// Company settings (name, phone, default price per kW, ...).
///
/// Falls back to the default row when the database has not been seeded yet, so
/// screens and PDFs can rely on a non-null value.
final settingsProvider = FutureProvider<AppSettings>((ref) async {
  final settings = await ref.read(settingsRepositoryProvider).getSettings();
  return settings ?? const AppSettings(id: 1);
});
