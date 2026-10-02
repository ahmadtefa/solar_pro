import '../../../../core/database/database_helper.dart';
import '../../../../core/errors/app_exception.dart';
import '../models/app_settings.dart';
import 'settings_repository.dart';

class SettingsRepositoryImpl implements SettingsRepository {
  final DatabaseHelper _db;

  SettingsRepositoryImpl(this._db);

  @override
  Future<AppSettings?> getSettings() async {
    try {
      return await _db.getAppSettings();
    } catch (e) {
      throw DatabaseException('Failed to get settings: $e');
    }
  }

  @override
  Future<int> updateSettings(AppSettings settings) async {
    try {
      return await _db.updateAppSettings(settings);
    } catch (e) {
      throw DatabaseException('Failed to update settings: $e');
    }
  }

  @override
  Future<void> resetSettings() async {
    try {
      await _db.updateAppSettings(const AppSettings(id: 1));
    } catch (e) {
      throw DatabaseException('Failed to reset settings: $e');
    }
  }
}
